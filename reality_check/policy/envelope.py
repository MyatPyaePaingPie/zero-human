"""Company spend envelope. Code decides authority; language never does.

Ported from money-swarm/automation/policy.py (ring policy engine + signed policy envelope).
The buyer's `max_budget_usd` is a request; this module is the company's answer. Every human
panel purchase passes through `check()` before `panel.launch()`. Fail closed:

- no envelope file, unparseable, expired, or bad signature  -> only free arms may run
- arm not in `allowed_arms`                                  -> deny
- price > per_job_cap_usd                                    -> deny
- today's evidence spend + price > daily_cap_usd             -> deny
- price > paid_usd * (1 - min_margin_ratio) when paid_usd>0  -> deny (never sell at a loss)

The LLM never sees or holds the envelope. Free text anywhere in a request cannot raise a cap.

Envelope file (default `state/envelope.json`, override RC_ENVELOPE):
{
  "daily_cap_usd": 60, "per_job_cap_usd": 10, "min_margin_ratio": 0.2,
  "allowed_arms": ["ensemble", "linq_panel", "terac_general"],
  "expires_at": "2026-08-15T23:59:00+00:00",
  "signed_by": "aria", "signature": "<hex sha256(secret + canonical body)>"
}
Signature secret comes from env RC_ENVELOPE_SECRET. Sign with `python -m reality_check.policy.envelope sign`.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from reality_check import store

ENVELOPE_PATH = Path(os.environ.get("RC_ENVELOPE", "state/envelope.json"))
FREE_ARMS = {"ensemble", "local"}
SIGNED_FIELDS = ("daily_cap_usd", "per_job_cap_usd", "min_margin_ratio", "allowed_arms", "expires_at", "signed_by")


@dataclass(frozen=True)
class SpendDecision:
    allow: bool
    reason: str
    envelope_live: bool
    spent_today_usd: float
    price_usd: float


def _canonical(body: dict) -> str:
    return json.dumps({k: body.get(k) for k in SIGNED_FIELDS}, sort_keys=True, separators=(",", ":"))


def sign(body: dict, secret: str) -> str:
    return hmac.new(secret.encode(), _canonical(body).encode(), hashlib.sha256).hexdigest()


def load(now: datetime | None = None, path: Path | None = None) -> tuple[dict | None, str]:
    """Return (envelope, reason). Envelope is None whenever anything is off."""
    path = path or ENVELOPE_PATH
    now = now or datetime.now(UTC)
    if not path.exists():
        return None, f"no envelope at {path}"
    try:
        body = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        return None, f"envelope unreadable: {exc}"
    try:
        exp = datetime.fromisoformat(body["expires_at"])
    except (KeyError, TypeError, ValueError):
        return None, "envelope has no valid expires_at"
    if exp.tzinfo is None or exp <= now:
        return None, "envelope expired or naive timestamp"
    secret = os.environ.get("RC_ENVELOPE_SECRET", "")
    if not secret:
        return None, "RC_ENVELOPE_SECRET unset; envelope cannot be verified"
    if not hmac.compare_digest(str(body.get("signature", "")), sign(body, secret)):
        return None, "envelope signature invalid"
    for k in ("daily_cap_usd", "per_job_cap_usd", "allowed_arms"):
        if k not in body:
            return None, f"envelope missing {k}"
    return body, "envelope live"


def spent_today(now: datetime | None = None) -> float:
    now = now or datetime.now(UTC)
    day = now.date().isoformat()
    with store.conn() as c:
        row = c.execute(
            "SELECT COALESCE(SUM(amount_usd),0) s FROM ledger WHERE kind LIKE 'cost.%' AND substr(created_at,1,10)=?",
            (day,),
        ).fetchone()
    return float(row["s"] if row else 0.0)


def check(*, arm: str, price_usd: float, paid_usd: float = 0.0, now: datetime | None = None) -> SpendDecision:
    """Pure function of (envelope file, ledger). Never raises."""
    try:
        spent = spent_today(now)
    except Exception as exc:  # store unavailable: fail closed
        return SpendDecision(False, f"ledger unreadable ({exc}); fail closed", False, 0.0, price_usd)
    if price_usd <= 0.0 and arm in FREE_ARMS:
        return SpendDecision(True, "free arm", False, spent, price_usd)
    env, why = load(now)
    if env is None:
        return SpendDecision(False, f"{why}; paid arms denied", False, spent, price_usd)
    if arm not in env["allowed_arms"]:
        return SpendDecision(False, f"arm {arm} not in envelope allowed_arms", True, spent, price_usd)
    if price_usd > float(env["per_job_cap_usd"]):
        return SpendDecision(False, f"price ${price_usd:.2f} exceeds per_job_cap ${float(env['per_job_cap_usd']):.2f}", True, spent, price_usd)
    if spent + price_usd > float(env["daily_cap_usd"]):
        return SpendDecision(False, f"daily cap ${float(env['daily_cap_usd']):.2f} would be exceeded (spent ${spent:.2f})", True, spent, price_usd)
    mm = float(env.get("min_margin_ratio", 0.0))
    if paid_usd > 0.0 and price_usd > paid_usd * (1.0 - mm):
        return SpendDecision(False, f"price ${price_usd:.2f} breaks margin floor on ${paid_usd:.2f} sale", True, spent, price_usd)
    return SpendDecision(True, "inside envelope", True, spent, price_usd)


def gate_panel_launch(job_id: str, arm: str, price_usd: float, paid_usd: float) -> bool:
    """Hook for judge.py. Records the decision as an event; True = launch may proceed."""
    try:
        d = check(arm=arm, price_usd=price_usd, paid_usd=paid_usd)
        store.event(job_id, "envelope.checked", asdict(d) | {"arm": arm})
        return d.allow
    except Exception as exc:
        try:
            store.event(job_id, "envelope.error", {"error": str(exc)})
        except Exception:
            pass
        return False


def bootstrap(example: Path = Path("state/envelope.example.json")) -> str:
    """On boot (Render has no shell): if RC_ENVELOPE_SECRET is set and no envelope exists,
    sign the example into ENVELOPE_PATH. Returns a one-line status for the event log."""
    secret = os.environ.get("RC_ENVELOPE_SECRET", "")
    if ENVELOPE_PATH.exists():
        return "envelope present"
    if not secret:
        return "no envelope and no RC_ENVELOPE_SECRET; paid arms stay denied"
    if not example.exists():
        return f"no {example}; paid arms stay denied"
    body = {k: v for k, v in json.loads(example.read_text()).items() if k in SIGNED_FIELDS}
    body["signature"] = sign(body, secret)
    ENVELOPE_PATH.parent.mkdir(parents=True, exist_ok=True)
    ENVELOPE_PATH.write_text(json.dumps(body, indent=2))
    return f"envelope signed into {ENVELOPE_PATH}"


def _cli(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] == "sign":
        secret = os.environ.get("RC_ENVELOPE_SECRET", "")
        if not secret:
            print("RC_ENVELOPE_SECRET unset", file=sys.stderr)
            return 2
        body = json.loads(ENVELOPE_PATH.read_text())
        body["signature"] = sign(body, secret)
        ENVELOPE_PATH.write_text(json.dumps(body, indent=2) + "\n")
        print(f"signed {ENVELOPE_PATH}")
        return 0
    env, why = load()
    print(json.dumps({"live": env is not None, "reason": why, "spent_today_usd": spent_today()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv))
