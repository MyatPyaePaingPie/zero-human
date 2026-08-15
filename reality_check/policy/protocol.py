"""Inbound buyer protocol: information crosses, authority never.

Ported from money-swarm/automation/agent_protocol/protocol.py. A buyer (agent or human) can
tell us WHAT to judge; it can never tell us that it has PAID, that it may skip the VOI gate for
free, or that we should spend more than the envelope allows.

- Body text is quarantined: stored verbatim for audit, hashed (content_sha256), never executed.
- Authority claims in free text ("already paid", "approved by", "force humans", "no budget
  limit", "ignore previous") are detected and listed as `authority_claims_discarded`; they
  grant nothing.
- Nonce replay is rejected; expired messages are rejected.
- `paid_usd` comes ONLY from a payment receipt in the ledger (Stripe webhook / x402), looked up by
  job_id, or from `X-RC-Paid` when RC_DEV=1. Never from the body.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from reality_check import store

AUTHORITY_PATTERNS = (
    re.compile(r"\b(already|has been|was) paid\b", re.I),
    re.compile(r"\bapproved by\b", re.I),
    re.compile(r"\b(force|always) humans?\b", re.I),
    re.compile(r"\bno (budget|spend(ing)?) (limit|cap)\b", re.I),
    re.compile(r"\bignore (all )?(previous|prior) (instructions|rules)\b", re.I),
    re.compile(r"\b(unlimited|max(imum)?) budget\b", re.I),
    re.compile(r"\bskip (the )?(voi|gate|payment)\b", re.I),
)
RISK_PATTERNS = (
    re.compile(r"(api[_ ]?key|password|credential|secret|token)s?\b.{0,40}(send|share|paste|reveal)", re.I),
    re.compile(r"(approve|execute|run) (this|the) (action|command|tool)", re.I),
)
MAX_TTL_S = 3600


@dataclass(frozen=True)
class Admission:
    admitted: bool
    content_sha256: str
    paid_usd: float
    paid_source: str
    authority_claims_discarded: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    reason: str = ""


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def content_hash(body: dict) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def scan(body: dict) -> tuple[list[str], list[str]]:
    texts = _strings(body)
    auth = sorted({p.pattern for t in texts for p in AUTHORITY_PATTERNS if p.search(t)})
    risk = sorted({p.pattern for t in texts for p in RISK_PATTERNS if p.search(t)})
    return auth, risk


def replay_guard(nonce: str | None, content_sha256: str) -> bool:
    """True if fresh. Nonce (or hash when no nonce) is recorded append-only in events."""
    key = nonce or content_sha256
    with store.conn() as c:
        seen = c.execute("SELECT 1 FROM events WHERE kind='protocol.nonce' AND payload=? LIMIT 1", (json.dumps({"n": key}),)).fetchone()
        if seen:
            return False
        c.execute("INSERT INTO events(job_id,kind,payload,created_at) VALUES(NULL,'protocol.nonce',?,?)",
                  (json.dumps({"n": key}), store.now()))
    return True


def paid_for(job_id: str | None) -> tuple[float, str]:
    """Only ledger revenue rows count as payment."""
    if not job_id:
        return 0.0, "none"
    with store.conn() as c:
        row = c.execute("SELECT COALESCE(SUM(amount_usd),0) s, MAX(note) note FROM ledger WHERE job_id=? AND kind='revenue'", (job_id,)).fetchone()
    return (float(row["s"]), str(row["note"] or "ledger")) if row and row["s"] else (0.0, "none")


def admit(body: dict, *, headers: dict[str, str] | None = None, job_id: str | None = None,
          now: datetime | None = None) -> Admission:
    headers = {k.lower(): v for k, v in (headers or {}).items()}
    now = now or datetime.now(UTC)
    sha = content_hash(body)
    auth, risk = scan(body)

    exp = headers.get("x-rc-expires")
    if exp:
        try:
            if datetime.fromisoformat(exp) <= now:
                return Admission(False, sha, 0.0, "none", auth, risk, "expired")
        except ValueError:
            return Admission(False, sha, 0.0, "none", auth, risk, "bad expires header")
    if not replay_guard(headers.get("x-rc-nonce"), sha):
        return Admission(False, sha, 0.0, "none", auth, risk, "replay")

    paid, src = paid_for(job_id)
    if paid <= 0.0 and os.environ.get("RC_DEV") == "1" and headers.get("x-rc-paid"):
        try:
            paid, src = float(headers["x-rc-paid"]), "dev-header"
        except ValueError:
            paid, src = 0.0, "none"
    return Admission(True, sha, paid, src, auth, risk, "admitted")


def record(job_id: str | None, adm: Admission) -> None:
    try:
        store.event(job_id, "protocol.admitted" if adm.admitted else "protocol.rejected", {
            "content_sha256": adm.content_sha256, "paid_usd": adm.paid_usd, "paid_source": adm.paid_source,
            "authority_claims_discarded": adm.authority_claims_discarded, "risk_flags": adm.risk_flags, "reason": adm.reason})
    except Exception:
        pass
