"""Verified Autonomous intake: a team submits claims + invariants + a live URL. Reasoning is
never accepted or stored (builder-blind verifier). The claims become a verified_autonomous job."""
from __future__ import annotations

from pydantic import BaseModel, Field

from reality_check import judge
from reality_check.core.models import JudgeRequest, Verdict


class IntakeRequest(BaseModel):
    team: str = Field(min_length=1, max_length=120)
    live_url: str = Field(min_length=4, max_length=500)
    claims: list[str] = Field(min_length=1, max_length=10, description="What the team says is autonomous, one checkable claim per line.")
    invariants: list[str] = Field(default_factory=list, max_length=10, description="What must never happen (e.g. 'no human approves a purchase').")
    paid_usd: float = 0.0


def submit(req: IntakeRequest) -> Verdict:
    text = (f"TEAM: {req.team}\nLIVE URL: {req.live_url}\n\nCLAIMS UNDER AUDIT:\n- " + "\n- ".join(req.claims)
            + ("\n\nINVARIANTS:\n- " + "\n- ".join(req.invariants) if req.invariants else "")
            + "\n\n(The verifier receives claims and invariants only. No builder reasoning.)")
    jr = JudgeRequest(input=text, claims=req.claims, sku="verified_autonomous", cost_if_wrong_usd=200.0,
                      max_budget_usd=10.0, buyer_id=f"team:{req.team}", force_humans=True,
                      human_question="Based on what you can see at the URL, does this claim hold? Yes or no, and what convinced you.")
    return judge.start(jr, paid_usd=req.paid_usd)
