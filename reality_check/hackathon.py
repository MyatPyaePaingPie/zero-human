"""Hackathon rubric evaluation: how to win THIS hackathon, from the bundle text.

Reads the one fenced JSON block in `docs/hackathon-rubric.md` (everything else there is prose for
humans), greps sponsor `evidence_hints` with zero model calls, and judges each rubric item with ONE
batched model call per section per persona (Groq free tier is ~30 RPM: never a per-claim call).

Deterministic given the votes: status/score/why/fix/stamp/top3 are pure functions of the p values.
Fail closed: a section whose evaluator raises gets status "unknown" and a warning; `evaluate` never
raises out.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from reality_check import evaluators

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RUBRIC = REPO_ROOT / "docs" / "hackathon-rubric.md"

SECTIONS = ("judging", "sponsors", "messaging", "technical")
ID_RE = re.compile(r"^(judge|sponsor|msg|tech)/[a-z0-9-]+$")

PASS_AT = 0.7
PARTIAL_AT = 0.4
QUALIFY_AT = 0.6          # per-claim bar for "majority of claims" in a sponsor track
CLAIMED_AT = 0.5          # mean p that counts as "the pitch says it uses this"
CHEAP_CLAIM_CHARS = 120   # a first claim short enough to be a single action before lock

_MSG_WHERE = {
    "msg/thesis": "deck slide 1 headline",
    "msg/first-screen": "landing page hero, above the fold",
    "msg/proof": "deck proof slide",
    "msg/tracks": "deck tracks slide",
    "msg/judge-fit": "deck slide on payments and craft",
}

@lru_cache(maxsize=8)
def _load(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise ValueError(f"hackathon rubric not found: {path}")
    text = p.read_text(encoding="utf-8")
    blocks = re.findall(r"```json\s*\n(.*?)\n```", text, flags=re.S)
    if not blocks:
        raise ValueError(f"no fenced ```json rubric block in {path}")
    if len(blocks) > 1:
        raise ValueError(f"expected exactly one fenced ```json block in {path}, found {len(blocks)}")
    try:
        data = json.loads(blocks[0])
    except json.JSONDecodeError as exc:
        raise ValueError(f"rubric json block in {path} does not parse: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"rubric json block in {path} is not an object")
    missing = [k for k in ("hackathon", *SECTIONS) if k not in data]
    if missing:
        raise ValueError(f"rubric json block in {path} is missing keys: {missing}")
    for sec in SECTIONS:
        items = data[sec]
        if not isinstance(items, list) or not items:
            raise ValueError(f"rubric section '{sec}' must be a non-empty list")
        for item in items:
            if not isinstance(item, dict) or not ID_RE.match(str(item.get("id", ""))):
                raise ValueError(f"rubric item in '{sec}' has a bad id: {item!r}")
            if not item.get("claims"):
                raise ValueError(f"rubric item {item.get('id')} has no claims")
    return data


def load_rubric(path: str | None = None) -> dict:
    """Parse (and cache) the fenced json rubric block. Raises ValueError with a clear message."""
    return _load(str(Path(path) if path else DEFAULT_RUBRIC))


def sponsor_evidence(text: str, rubric: dict) -> dict[str, list[str]]:
    """Per sponsor id: which evidence_hints actually appear in the bundle text. Zero model calls."""
    low = (text or "").lower()
    out: dict[str, list[str]] = {}
    for sp in rubric.get("sponsors", []):
        found = []
        for hint in sp.get("evidence_hints", []):
            h = str(hint).lower().strip()
            if h and h in low:
                found.append(str(hint))
        out[str(sp.get("id"))] = found
    return out


# --------------------------------------------------------------------------- scoring primitives

def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _status(mean_p: float) -> str:
    if mean_p >= PASS_AT:
        return "pass"
    if mean_p >= PARTIAL_AT:
        return "partial"
    return "fail"


def _claim_rows(claims: list[str], results: list[list]) -> list[dict]:
    """results[i] = list of Vote for claim i, across every persona."""
    rows = []
    for text, votes in zip(claims, results):
        ps = [float(v.forecast.p) for v in votes]
        p = round(_mean(ps), 4)
        reasons = sorted((str(v.forecast.reasoning or "") for v in votes), key=len)
        rows.append({
            "text": text,
            "p": p,
            "side": "yes" if p > 0.5 else "no",
            "evidence_state": "model",
            "reasoning": reasons[0] if reasons else "",
        })
    return rows


def _why_fix(rows: list[dict]) -> tuple[str, str]:
    if not rows:
        return "weakest: no model answer", "No claim was judged; re-run."
    weakest = min(rows, key=lambda r: r["p"])
    return (f"weakest: {weakest['text']}",
            f"Make this visibly true and state it where a judge looks first (hero line, slide 1 or 2, "
            f"README first paragraph): {weakest['text']}")


def _unknown_rows(claims: list[str]) -> list[dict]:
    return [{"text": c, "p": 0.0, "side": "no", "evidence_state": "model",
             "reasoning": "evaluator unavailable"} for c in claims]


def _run_section(items: list[dict], text: str, personas: tuple[str, ...],
                 warnings: list[str], section: str) -> tuple[list[list[dict]], bool, int]:
    """One evaluate_batch call per persona over every claim in the section. Returns per-item claim
    rows, whether the section is unknown (evaluator raised), and the number of model calls made."""
    claims: list[str] = []
    spans: list[tuple[int, int]] = []
    for item in items:
        start = len(claims)
        claims.extend(str(c) for c in item.get("claims", []))
        spans.append((start, len(claims)))
    calls = 0
    per_claim_votes: list[list] = [[] for _ in claims]
    for persona in personas:
        try:
            results = evaluators.evaluate_batch(claims, text, [persona])
            calls += 1
        except Exception as exc:  # fail closed: the section goes unknown, evaluate never raises
            warnings.append(f"{section}: evaluator failed ({exc}); items marked unknown")
            return [_unknown_rows(claims[a:b]) for a, b in spans], True, calls
        for i, res in enumerate(results[:len(claims)]):
            per_claim_votes[i].extend(res.votes)
    rows = _claim_rows(claims, per_claim_votes)
    return [rows[a:b] for a, b in spans], False, calls


# --------------------------------------------------------------------------- sponsors

def _sponsor_bucket(sp: dict, rows: list[dict], hints: list[str], unknown: bool) -> str:
    """Evidence hints (grep over README, file names, manifests, page) decide USED or NOT; the model
    only grades how well the pitch shows it. No hint = not used (or cheapest to add when the
    sponsor is required or the first claim is a cheap one-liner)."""
    ps = [r["p"] for r in rows]
    majority = len([p for p in ps if p >= QUALIFY_AT]) * 2 > len(ps) if ps else False
    if hints:
        return "qualifies" if (majority and not unknown) else "claimed_not_evidenced"
    first = str((sp.get("claims") or [""])[0])
    if sp.get("required") or len(first) <= CHEAP_CLAIM_CHARS:
        return "cheapest_to_add"
    return "not_used"


def _sponsors(rubric: dict, text: str, rows_by_item: list[list[dict]], unknown: bool) -> dict:
    hints = sponsor_evidence(text, rubric)
    buckets: dict[str, list[dict]] = {"qualifies": [], "claimed_not_evidenced": [],
                                      "cheapest_to_add": [], "not_used": []}
    for sp, rows in zip(rubric.get("sponsors", []), rows_by_item):
        found = hints.get(str(sp.get("id")), [])
        bucket = _sponsor_bucket(sp, rows, found, unknown)
        why, fix = _why_fix(rows)
        entry = {
            "id": sp.get("id"),
            "name": sp.get("name"),
            "required": bool(sp.get("required")),
            "hints_found": found,
            "claims": rows,
            "status": ("unknown" if unknown else _status(_mean([r["p"] for r in rows])) if found else "not_used"),
            "why": why if found else "no evidence of this sponsor in the repo, manifests, or page",
            "fix": fix if found else f"Not used. Cheapest way in: {str((sp.get('claims') or [''])[0])}",
        }
        buckets[bucket].append(entry)
    extra = sorted(buckets["cheapest_to_add"], key=lambda e: (not e["required"],))
    buckets["cheapest_to_add"] = extra[:3]
    buckets["not_used"].extend(extra[3:])
    return buckets


# --------------------------------------------------------------------------- messaging

def _rewrite(item: dict, rows: list[dict]) -> str:
    if not rows:
        return f"Write one line for '{item.get('theme', item.get('id'))}' and put it on the first screen."
    weakest = min(rows, key=lambda r: r["p"])
    line = re.sub(r"^(The pitch|The deck|The headline|There is|It)\s+", "", weakest["text"]).strip()
    line = line[0].upper() + line[1:] if line else weakest["text"]
    return f"Put one line on the first screen that makes this true: {line}"


# --------------------------------------------------------------------------- public entry point

def evaluate(text: str, *, has_repo: bool, rubric: dict | None = None,
             personas: tuple[str, ...] = ("judge", "customer")) -> dict:
    """Judge a bundle (README + manifests + slides + page text) against the hackathon rubric."""
    rubric = rubric or load_rubric()
    warnings: list[str] = []
    calls = 0

    judging_items = list(rubric.get("judging", []))
    j_rows, j_unknown, c = _run_section(judging_items, text, personas, warnings, "judging")
    calls += c
    judging = []
    for item, rows in zip(judging_items, j_rows):
        why, fix = _why_fix(rows)
        mean_p = _mean([r["p"] for r in rows])
        judging.append({
            "id": item.get("id"), "title": item.get("title"), "weight": int(item.get("weight", 1)),
            "status": "unknown" if j_unknown else _status(mean_p),
            "score": round(mean_p, 4), "why": why, "fix": fix, "claims": rows,
        })
    judging.sort(key=lambda i: -i["weight"])

    sponsor_items = list(rubric.get("sponsors", []))
    s_rows, s_unknown, c = _run_section(sponsor_items, text, personas, warnings, "sponsors")
    calls += c
    sponsors = _sponsors(rubric, text, s_rows, s_unknown)

    msg_items = list(rubric.get("messaging", []))
    m_rows, m_unknown, c = _run_section(msg_items, text, personas, warnings, "messaging")
    calls += c
    messaging = []
    for item, rows in zip(msg_items, m_rows):
        mean_p = _mean([r["p"] for r in rows])
        messaging.append({
            "id": item.get("id"), "theme": item.get("theme"),
            "status": "unknown" if m_unknown else _status(mean_p),
            "rewrite": _rewrite(item, rows),
            "where": _MSG_WHERE.get(str(item.get("id")), "deck slide 1 / landing hero"),
            "claims": rows,
        })

    technical: list[dict] = []
    if has_repo:
        tech_items = list(rubric.get("technical", []))
        t_rows, t_unknown, c = _run_section(tech_items, text, personas, warnings, "technical")
        calls += c
        for item, rows in zip(tech_items, t_rows):
            why, fix = _why_fix(rows)
            mean_p = _mean([r["p"] for r in rows])
            technical.append({
                "id": item.get("id"), "title": item.get("title"),
                "status": "unknown" if t_unknown else _status(mean_p),
                "score": round(mean_p, 4), "why": why, "fix": fix, "claims": rows,
            })

    # autonomy: "can this run autonomously?" graded against how agent-run companies fail
    # (rubric.autonomy.items, ids auto/*); its own stamp, always run
    autonomy: list[dict] = []
    auto_items = list((rubric.get("autonomy") or {}).get("items", []))
    if auto_items:
        a_rows, a_unknown, c = _run_section(auto_items, text, personas, warnings, "autonomy")
        calls += c
        for item, rows in zip(auto_items, a_rows):
            why, fix = _why_fix(rows)
            mean_p = _mean([r["p"] for r in rows])
            autonomy.append({
                "id": item.get("id"), "title": item.get("title"), "failure": item.get("failure"),
                "status": "unknown" if a_unknown else _status(mean_p),
                "score": round(mean_p, 4), "why": why, "fix": fix, "claims": rows,
            })
    n_pass = sum(1 for a in autonomy if a["status"] == "pass")
    n_fail = sum(1 for a in autonomy if a["status"] == "fail")
    autonomy_stamp = ("not_run" if not autonomy else "autonomous" if n_fail == 0 and n_pass >= len(autonomy) - 1
                      else "human_in_the_loop" if n_fail <= 2 else "not_autonomous")

    out = {
        "rubric_version": rubric.get("hackathon", ""),
        "autonomy": autonomy,
        "autonomy_stamp": autonomy_stamp,
        "autonomy_note": (rubric.get("autonomy") or {}).get("note", ""),
        "submission_checklist": rubric.get("submission_checklist", {}),
        "personas": list(personas),
        "model_calls": calls,
        "judging": judging,
        "sponsors": sponsors,
        "messaging": messaging,
        "technical": technical,
        "stamp": _stamp(judging, sponsors),
        "top3": _top3(judging, sponsors, messaging),
        "warnings": warnings,
    }
    return out


def _stamp(judging: list[dict], sponsors: dict) -> str:
    heavy = [i for i in judging if i["weight"] >= 3]
    required = [e for bucket in sponsors.values() for e in bucket if e["required"]]
    qualified = {e["id"] for e in sponsors["qualifies"]}
    claimed = qualified | {e["id"] for e in sponsors["claimed_not_evidenced"]}
    req_qualifies = all(e["id"] in qualified for e in required)
    req_claimed = all(e["id"] in claimed for e in required)
    if heavy and all(i["status"] == "pass" for i in heavy) and req_qualifies:
        return "contender"
    if not any(i["status"] in ("fail", "unknown") for i in heavy) and req_claimed:
        return "fixable_by_1830"
    return "not_yet"


def _top3(judging: list[dict], sponsors: dict, messaging: list[dict]) -> list[str]:
    out: list[str] = []
    failing = [i for i in judging if i["status"] in ("fail", "partial", "unknown")]
    failing.sort(key=lambda i: (-i["weight"], i["score"]))
    for i in failing:
        out.append(f"{i['title']}: {i['fix']}")
    for e in sponsors["cheapest_to_add"] + sponsors["claimed_not_evidenced"]:
        if e["required"] or len(out) < 3:
            out.append(f"{e['name']}: {e['fix']}")
    for m in messaging:
        if m["status"] in ("fail", "partial", "unknown"):
            out.append(f"{m['where']}: {m['rewrite']}")
    return out[:3]
