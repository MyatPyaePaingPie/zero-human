"""Shared models. Forecast is inlined from augur.llm.schema so consensus.py vendors cleanly."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Side = Literal["yes", "no", "skip"]


class Forecast(BaseModel):
    """One evaluator's answer to a binary judgment question. p = P(answer is YES)."""
    model_config = ConfigDict(extra="forbid")

    p: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(min_length=1, max_length=4000)
    refuted_by: list[str] = Field(default_factory=list)
    side: Side = "skip"
    forecast_mean: float | None = None


class JudgeRequest(BaseModel):
    """What a buyer (agent or human) sends to POST /judge.

    Every question is normalised to a binary claim so evaluators, humans and settlement
    share one currency: p = P(claim is true). "Which is better, A or B" becomes the claim
    "A is better than B".
    """
    model_config = ConfigDict(extra="forbid")

    input: str = Field(min_length=1, max_length=20000, description="Text, URL, or A/B payload.")
    claim: str | None = Field(default=None, max_length=500, description="Single binary claim (shorthand for claims=[claim]).")
    claims: list[str] = Field(default_factory=list, max_length=12, description="Rubric: several binary claims judged together.")
    human_question: str | None = Field(default=None, max_length=300, description="Free-text question shown to humans; defaults to the claim(s).")
    sku: Literal["reality_check", "demand_check", "verified_autonomous", "custom"] = "reality_check"
    personas: list[str] | None = Field(default=None, description="Evaluator persona ids; defaults per SKU.")
    audience: Literal["general", "expert"] = "general"
    max_budget_usd: float = Field(default=8.0, ge=0.0, le=500.0)
    desired_confidence: float = Field(default=0.8, ge=0.5, le=0.99)
    cost_if_wrong_usd: float = Field(default=50.0, ge=0.0, description="Buyer's stake: what acting on a wrong verdict costs.")
    buyer_id: str = "anonymous"
    force_humans: bool = Field(default=False, description="Room SKU: humans were sold, skip the VOI gate and always launch a panel.")

    @model_validator(mode="after")
    def _normalise_claims(self) -> "JudgeRequest":
        if self.claim and not self.claims:
            self.claims = [self.claim]
        if not self.claims:
            from reality_check.skus import default_claims
            self.claims = default_claims(self.sku)
        if not self.claims:
            raise ValueError("at least one claim is required")
        self.claim = self.claims[0]
        if self.personas:
            from reality_check.evaluators import PERSONAS
            bad = [x for x in self.personas if x not in PERSONAS]
            if bad:
                raise ValueError(f"unknown personas {bad}; valid: {sorted(PERSONAS)}")
        return self


class ClaimVerdict(BaseModel):
    claim: str
    verdict: Literal["yes", "no", "undecided"]
    p_internal: float
    agreement: float
    p_humans: float | None = None
    n_humans: int = 0
    minority_view: str = ""


class VoiDecision(BaseModel):
    buy: bool
    p_internal: float
    p_wrong_without: float
    p_wrong_with: float
    expected_loss_without: float
    expected_loss_with: float
    evidence_price_usd: float
    net_value_usd: float
    arm: str | None
    reason: str


class Verdict(BaseModel):
    job_id: str
    status: Literal["pending_payment", "evaluating", "awaiting_humans", "settled", "failed"]
    verdict: Literal["yes", "no", "undecided"]
    p: float
    confidence: float
    agreement: float
    n_evaluators: int
    n_humans: int
    summary: str
    minority_view: str
    claims: list[ClaimVerdict] = Field(default_factory=list)
    voi: VoiDecision | None = None
    human_answers: list[dict] = Field(default_factory=list)
    revenue_usd: float = 0.0
    evidence_cost_usd: float = 0.0
    margin_usd: float = 0.0
