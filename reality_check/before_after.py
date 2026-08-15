"""Pre-registered before/after. Ported from money-swarm/automation/experiments.py.

The hackathon asks for a measurable before/after from human input. "It improved" is a claim; a
receipt is a hash locked BEFORE the humans answer plus a critic record bound to both verdicts.

Flow:
  lock(before_job_id)                 -> hash of the before verdict is stored (event before_after.locked)
  compare(before_job_id, after_job_id) -> delta per claim + overall, critic receipt with both hashes

Rules (money-swarm failure mode #15): a comparison is `invalid` (not pass/fail) when the after
job has no human answers, when the before hash was not locked, or when the inputs are identical.
"""
from __future__ import annotations

import hashlib
import json

from reality_check import judge, store


def _vhash(job_id: str) -> str:
    v = judge.verdict(job_id).model_dump()
    v.pop("status", None)
    return hashlib.sha256(json.dumps(v, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def lock(before_job_id: str) -> str:
    h = _vhash(before_job_id)
    store.event(before_job_id, "before_after.locked", {"before_hash": h})
    return h


def _locked(before_job_id: str) -> tuple[str, str] | None:
    """Latest lock (hash, created_at). Re-locking is allowed until the after job's humans answer."""
    with store.conn() as c:
        row = c.execute("SELECT payload, created_at FROM events WHERE job_id=? AND kind='before_after.locked' ORDER BY id DESC LIMIT 1",
                        (before_job_id,)).fetchone()
    return (json.loads(row["payload"])["before_hash"], row["created_at"]) if row else None


def _first_human_at(job_id: str) -> str | None:
    with store.conn() as c:
        row = c.execute("SELECT MIN(created_at) t FROM human_answers WHERE job_id=?", (job_id,)).fetchone()
    return row["t"] if row and row["t"] else None


def compare(before_job_id: str, after_job_id: str) -> dict:
    b, a = judge.verdict(before_job_id), judge.verdict(after_job_id)
    bj, aj = store.get_job(before_job_id), store.get_job(after_job_id)
    lk = _locked(before_job_id)
    locked = lk[0] if lk else None
    first_after = _first_human_at(after_job_id)
    decision, why = "measured", ""
    if lk is None:
        decision, why = "invalid", "before verdict was not locked"
    elif locked != _vhash(before_job_id):
        decision, why = "invalid", "before verdict changed after lock"
    elif first_after is not None and lk[1] > first_after:
        decision, why = "invalid", "lock happened after the after-job's humans started answering"
    elif a.n_humans == 0:
        decision, why = "invalid", "after job has no human answers"
    elif bj and aj and bj["request"]["input"] == aj["request"]["input"]:
        decision, why = "invalid", "before and after inputs are identical"
    elif bj and aj and (bj["request"]["sku"], bj["request"]["claims"], bj["request"].get("personas")) != \
            (aj["request"]["sku"], aj["request"]["claims"], aj["request"].get("personas")):
        decision, why = "invalid", "before and after are not comparable (sku, claims, or personas differ)"
    else:
        shared = {x["respondent"] for x in store.human_answers(before_job_id)} & {x["respondent"] for x in store.human_answers(after_job_id)}
        if shared:
            decision, why = "invalid", f"{len(shared)} respondent(s) judged both versions; after-job needs fresh eyes"

    per_claim = []
    for i, bc in enumerate(b.claims):
        ac = a.claims[i] if i < len(a.claims) else None
        pb = bc.p_humans if bc.p_humans is not None else bc.p_internal
        pa = (ac.p_humans if ac.p_humans is not None else ac.p_internal) if ac else None
        per_claim.append({"claim": bc.claim, "before_p": pb, "after_p": pa,
                          "delta": None if pa is None else round(pa - pb, 3),
                          "before_verdict": bc.verdict, "after_verdict": ac.verdict if ac else None})
    improved = [c for c in per_claim if c["delta"] is not None and c["delta"] > 0]
    result = {
        "decision": decision, "why": why, "locked_at": lk[1] if lk else None,
        "before": {"job_id": before_job_id, "p": b.p, "verdict": b.verdict, "n_humans": b.n_humans, "hash": locked},
        "after": {"job_id": after_job_id, "p": a.p, "verdict": a.verdict, "n_humans": a.n_humans, "hash": _vhash(after_job_id)},
        "delta_p": round(a.p - b.p, 3), "claims_improved": len(improved), "claims_total": len(per_claim),
        "per_claim": per_claim,
        "evidence_cost_usd": round(b.evidence_cost_usd + a.evidence_cost_usd, 4),
        "revenue_usd": round(b.revenue_usd + a.revenue_usd, 2),
    }
    receipt = {"kind": "critic", "decision_hash": hashlib.sha256(json.dumps(result, sort_keys=True, default=str).encode()).hexdigest(),
               "verdict": "approve" if decision == "measured" else "reject", "critic_id": "before_after.compare"}
    result["critic_receipt"] = receipt
    store.event(after_job_id, "before_after.compared", {"before": before_job_id, "decision": decision,
                                                         "delta_p": result["delta_p"], "critic": receipt})
    return result
