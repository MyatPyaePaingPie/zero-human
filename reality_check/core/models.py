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

    input: str = Field(default="", max_length=20000, description="Text, URL, or A/B payload. May be empty when repo/deck/url are given.")
    repo: str | None = Field(default=None, max_length=300, description="GitHub repo URL: README + manifests are read via the API (no clone) and merged into the input.")
    deck: str | None = Field(default=None, max_length=500, description="Deck: PDF URL or public Google Slides link (exported as PDF); slide text is merged into the input.")
    claim: str | None = Field(default=None, max_length=500, description="Single binary claim (shorthand for claims=[claim]).")
    claims: list[str] = Field(default_factory=list, max_length=64, description="Rubric: several binary claims judged together.")
    human_question: str | None = Field(default=None, max_length=300, description="Free-text question shown to humans; defaults to the claim(s).")
    sku: Literal["reality_check", "demand_check", "verified_autonomous", "full_reality_check", "custom"] = "reality_check"
    extra_claims: list[str] = Field(default_factory=list, max_length=8, description="full_reality_check: the team's own autonomy claims, appended after the preset lenses.")
    personas: list[str] | None = Field(default=None, description="Evaluator persona ids; defaults per SKU.")
    audience: Literal["general", "expert"] = "general"
    max_budget_usd: float = Field(default=8.0, ge=0.0, le=500.0)
    desired_confidence: float = Field(default=0.8, ge=0.5, le=0.99)
    cost_if_wrong_usd: float = Field(default=50.0, ge=0.0, description="Buyer's stake: what acting on a wrong verdict costs.")
    buyer_id: str = "anonymous"
    evidence_standard: Literal["voi_routed", "human_backed", "expert_backed"] | None = Field(
        default=None, description="Floor the router must satisfy (defaults per SKU). voi_routed: buy only what VOI says pays. "
        "human_backed: not final until >=3 real people judged; router still picks the cheapest satisfying arm. expert_backed: Terac expert.")
    force_humans: bool = Field(default=False, description="Deprecated alias for evidence_standard=human_backed.")
    before_job_id: str | None = Field(default=None, max_length=32, description="Before/after: the earlier job this one is measured against; its respondents are refused here.")
    notify_phone: str | None = Field(default=None, max_length=20, description="E.164 phone; the verdict is texted here (Linq) when the job settles.")
    url: str | None = Field(default=None, max_length=500, description="Live URL: probes.py runs objective checks (SEO/accessibility/security/agent-ready) against it in the background.")

    @model_validator(mode="after")
    def _normalise_claims(self) -> "JudgeRequest":
        if not (self.input.strip() or self.repo or self.deck or self.url):
            raise ValueError("give at least one of input, repo, deck, url")
        if self.claim and not self.claims:
            self.claims = [self.claim]
        if not self.claims:
            from reality_check.skus import default_claims
            self.claims = default_claims(self.sku)
        if self.extra_claims:
            self.claims = self.claims + [c for c in self.extra_claims if c not in self.claims]
        if not self.claims:
            raise ValueError("at least one claim is required")
        self.claim = self.claims[0]
        if self.evidence_standard is None:
            from reality_check.skus import default_standard
            self.evidence_standard = "human_backed" if self.force_humans else default_standard(self.sku)
        self.force_humans = self.evidence_standard != "voi_routed"
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
    objective: dict | None = Field(default=None, description="Replay QA journey evidence for flow claims: {result, bugs, journey_id}.")
    lens: str = "custom"
    claim_id: str = Field(default="", description="Stable `<lens>/<slug>` id; the agent report (#4) keys findings on it.")
    evidence_state: Literal["none", "probe", "model", "human"] = Field(
        default="model", description="What actually backs this verdict. 'none' = objective claim with no probe run yet: "
        "render as 'no evidence yet: give a live URL', never as a model opinion.")


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
