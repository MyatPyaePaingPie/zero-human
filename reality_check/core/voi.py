"""Value-of-information gate: should this decision buy external judgment?

Written fresh; augur has no VOI. Only the gate SHAPE is inherited from augur's kelly.py:
fail closed, floors, capped spend, every constant that could flip the sign is a named
parameter with a stated default rather than a magic number.

Currency is expected dollar loss. The buyer acts on the internal majority. Under the
internal belief p, P(acting wrong) = 1 - max(p, 1-p). Self-reported LLM confidence was
anti-predictive in augur, so it is NOT used; disagreement between evaluators
(dissent) is what widens p_wrong toward 0.5.

    E_loss_without = p_wrong * cost_if_wrong
    E_loss_with    = p_wrong * (1 - gain(arm)) * cost_if_wrong
    buy iff  E_loss_without - E_loss_with > price(arm) + MARGIN

gain(arm) is the measured fraction of internal error the evidence source removes,
estimated from settled jobs (brier vs human oracle); before n_settled >= MIN_SETTLED it
uses a conservative prior per arm and says so in `reason`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from reality_check.core.models import VoiDecision

PANEL_N = 5                                                       # humans per panel (judge.HUMAN_TARGET_N)
TERAC_CPI_USD = float(os.environ.get("TERAC_CPI_USD", "1.0"))    # per-response planning price; set from the booth quote
TERAC_EXPERT_CPI_USD = float(os.environ.get("TERAC_EXPERT_CPI_USD", "28.0"))

MIN_SETTLED = 10          # below this, gain is the prior, not a measurement
MARGIN_USD = 0.25         # must clear price by this, not at breakeven
DISSENT_WIDENING = 0.5    # p_wrong += dissent * DISSENT_WIDENING * (0.5 - p_wrong)
CONFIDENCE_FLOOR = 0.55   # if internal p_wrong <= 1-floor and no dissent, do not buy


@dataclass(frozen=True)
class EvidenceArm:
    name: str
    price_usd: float
    latency_s: float
    prior_gain: float                # fraction of internal error removed, prior belief
    measured_gain: float | None = None
    n_settled: int = 0

    @property
    def gain(self) -> float:
        if self.measured_gain is not None and self.n_settled >= MIN_SETTLED:
            return max(0.0, min(1.0, self.measured_gain))
        return self.prior_gain


DEFAULT_ARMS: tuple[EvidenceArm, ...] = (
    EvidenceArm("ensemble", price_usd=0.02, latency_s=15, prior_gain=0.15),
    EvidenceArm("linq_panel", price_usd=1.00, latency_s=300, prior_gain=0.45),
    EvidenceArm("terac_general", price_usd=TERAC_CPI_USD * PANEL_N, latency_s=3600, prior_gain=0.60),
    EvidenceArm("terac_expert", price_usd=TERAC_EXPERT_CPI_USD, latency_s=21600, prior_gain=0.75),
)


def p_wrong_without(p_internal: float, dissent: float) -> float:
    base = 1.0 - max(p_internal, 1.0 - p_internal)
    d = max(0.0, min(1.0, dissent))
    return base + d * DISSENT_WIDENING * (0.5 - base)


def decide(
    *,
    p_internal: float,
    dissent: float,
    cost_if_wrong_usd: float,
    max_budget_usd: float,
    arms: tuple[EvidenceArm, ...] = DEFAULT_ARMS,
    max_latency_s: float | None = None,
) -> VoiDecision:
    pw = p_wrong_without(p_internal, dissent)
    e_without = pw * cost_if_wrong_usd

    if pw <= (1.0 - CONFIDENCE_FLOOR) and dissent == 0.0:
        return VoiDecision(
            buy=False, p_internal=p_internal, p_wrong_without=pw, p_wrong_with=pw,
            expected_loss_without=e_without, expected_loss_with=e_without,
            evidence_price_usd=0.0, net_value_usd=0.0, arm=None,
            reason="internal evaluators agree with margin; more evidence not worth buying",
        )

    best: tuple[float, EvidenceArm, float] | None = None
    for arm in arms:
        if arm.price_usd > max_budget_usd:
            continue
        if max_latency_s is not None and arm.latency_s > max_latency_s:
            continue
        pw_with = pw * (1.0 - arm.gain)
        e_with = pw_with * cost_if_wrong_usd
        net = (e_without - e_with) - arm.price_usd - MARGIN_USD
        if best is None or net > best[0]:
            best = (net, arm, pw_with)

    if best is None or best[0] <= 0.0:
        arm_name = best[1].name if best else None
        return VoiDecision(
            buy=False, p_internal=p_internal, p_wrong_without=pw, p_wrong_with=pw,
            expected_loss_without=e_without, expected_loss_with=e_without,
            evidence_price_usd=best[1].price_usd if best else 0.0,
            net_value_usd=best[0] if best else 0.0, arm=arm_name,
            reason="no evidence source clears its price within budget/latency (fail closed)",
        )

    net, arm, pw_with = best
    measured = arm.measured_gain is not None and arm.n_settled >= MIN_SETTLED
    return VoiDecision(
        buy=True, p_internal=p_internal, p_wrong_without=pw, p_wrong_with=pw_with,
        expected_loss_without=e_without, expected_loss_with=pw_with * cost_if_wrong_usd,
        evidence_price_usd=arm.price_usd, net_value_usd=net, arm=arm.name,
        reason=(f"buy {arm.name}: removes {arm.gain:.0%} of expected error "
                f"({'measured' if measured else 'prior, n<'+str(MIN_SETTLED)}) for ${arm.price_usd:.2f}"),
    )
