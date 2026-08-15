"""Sweep: judge a batch of uncurated products (Product Hunt launches) with NO money attached.

Purpose: calibration input before humans. Every item runs evidence_standard=voi_routed and unpaid,
so the envelope forbids any paid arm and only the free model evaluators run; the router's
buy/decline decisions and per-claim verdicts accumulate as real, uncurated data on the dashboard.
Publishing them (GET /sweep) as "clarity checks with a fix list" is content, not outreach.
"""
from __future__ import annotations

import threading
import uuid

from pydantic import BaseModel, Field

from reality_check import judge, store
from reality_check.core.models import JudgeRequest

SWEEP_CLAIMS = [
    "A first-time visitor can tell what this product does within ten seconds",
    "The tagline names who it is for",
    "The tagline names a problem the reader already recognizes",
]


class SweepItem(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    tagline: str = Field(default="", max_length=300)
    description: str = Field(default="", max_length=6000)
    url: str = Field(default="", max_length=500)
    source: str = Field(default="producthunt", max_length=40)


class SweepRequest(BaseModel):
    items: list[SweepItem] = Field(min_length=1, max_length=20)
    cost_if_wrong_usd: float = Field(default=20.0, ge=0.0)


def start_background(req: SweepRequest) -> dict:
    """Return immediately; items are judged one by one in a daemon thread (evaluators are slow
    on free tiers and a 20-item batch outlives any HTTP timeout)."""
    t = threading.Thread(target=run, args=(req,), daemon=True, name="sweep")
    t.start()
    store.event(None, "sweep.started", {"n": len(req.items), "source": req.items[0].source})
    return {"queued": len(req.items), "watch": "/sweep"}


def run(req: SweepRequest) -> list[dict]:
    out = []
    for it in req.items:
        text = f"{it.name}\n{it.tagline}\n\n{it.description}".strip()
        jr = JudgeRequest(input=text[:20000], claims=SWEEP_CLAIMS, sku="custom", evidence_standard="voi_routed",
                          cost_if_wrong_usd=req.cost_if_wrong_usd, max_budget_usd=0.0, buyer_id=f"sweep:{it.source}",
                          personas=["outsider", "buyer", "skeptic"])
        job_id = uuid.uuid4().hex[:12]
        v = judge.start(jr, paid_usd=0.0, job_id=job_id)
        job = store.get_job(job_id)
        job["state"]["sweep"] = {"name": it.name, "tagline": it.tagline, "url": it.url, "source": it.source}
        store.put_job(job_id, job["buyer_id"], job["status"], job["request"], job["state"])
        out.append({"job_id": job_id, "name": it.name, "verdict": v.verdict, "p": v.p, "voi": v.voi.model_dump() if v.voi else None,
                    "claims": [{"claim": c.claim, "verdict": c.verdict, "p": c.p_internal} for c in v.claims], "summary": v.summary})
    store.event(None, "sweep.done", {"n": len(out)})
    return out


def listing(limit: int = 100) -> list[dict]:
    rows = []
    for j in store.list_jobs(limit=500):
        sw = (j.get("state") or {}).get("sweep")
        if not sw:
            continue
        v = judge.verdict(j["job_id"])
        rows.append({"job_id": j["job_id"], **sw, "verdict": v.verdict, "p": v.p, "status": v.status,
                     "voi": {"buy": v.voi.buy, "arm": v.voi.arm, "reason": v.voi.reason} if v.voi else None,
                     "claims": [{"claim": c.claim, "verdict": c.verdict, "p": c.p_internal, "minority": c.minority_view} for c in v.claims],
                     "n_humans": v.n_humans})
        if len(rows) >= limit:
            break
    return rows
