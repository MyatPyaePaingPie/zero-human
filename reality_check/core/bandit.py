"""Hybrid bandit allocator — Thompson + UCB1 + ε-greedy + uniform.

Allocates capital across strategy arms. Each tick, one policy is sampled
according to ``POLICY_WEIGHTS``; that policy returns a top arm. The top arm
gets ``TOP_SHARE`` of the bankroll. Arms above the median sample value split
the next ``ABOVE_MEDIAN_SHARE``. Every arm currently in TESTING gets at
least ``TESTING_FLOOR``.

Rationale:
* Pure Thompson is greedy in expectation. Mixing policies + a floor for under-
  sampled arms is the cheapest robust defense against local-maxima lock-in.
* The reward signal is Brier-improvement-vs-crowd, NOT raw PnL. PnL is noisy
  at low N; Brier converges 5-10x faster and is the actual edge we pay for.
"""
from __future__ import annotations

import math
import random
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

POLICY_WEIGHTS: dict[str, float] = {
    "thompson":       0.60,
    "ucb1":           0.20,
    "epsilon_greedy": 0.10,
    "uniform":        0.10,
}
EPSILON = 0.15
TOP_SHARE = 0.50
ABOVE_MEDIAN_SHARE = 0.40
TESTING_FLOOR = 0.05
UCB_C = math.sqrt(2.0)

Policy = Literal["thompson", "ucb1", "epsilon_greedy", "uniform"]


@dataclass(frozen=True)
class Arm:
    hypothesis_id: str
    alpha: float           # Beta posterior wins
    beta: float            # Beta posterior losses
    ucb_n: int             # pull count
    ucb_sum: float         # sum of rewards in [0, 1]
    status: str            # 'testing'|'supported'|... mirrors hypotheses.status


@dataclass(frozen=True)
class Allocation:
    tick_id: str
    ts: str
    policy: Policy
    allocations: dict[str, float]   # hypothesis_id -> bankroll fraction in [0, 1]
    rationale: str

    def total(self) -> float:
        return sum(self.allocations.values())


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# ---- individual policies ---------------------------------------------------

def thompson_sample(arms: list[Arm], rng: random.Random) -> dict[str, float]:
    """Sample one draw from each arm's Beta(α, β); return {arm_id: sample}."""
    return {a.hypothesis_id: rng.betavariate(max(a.alpha, 1e-6), max(a.beta, 1e-6)) for a in arms}


def ucb1_scores(arms: list[Arm]) -> dict[str, float]:
    total_n = max(sum(a.ucb_n for a in arms), 1)
    out: dict[str, float] = {}
    for a in arms:
        if a.ucb_n == 0:
            out[a.hypothesis_id] = float("inf")  # force first pull
            continue
        mean = a.ucb_sum / a.ucb_n
        bonus = UCB_C * math.sqrt(math.log(total_n) / a.ucb_n)
        out[a.hypothesis_id] = mean + bonus
    return out


def epsilon_greedy_scores(arms: list[Arm], rng: random.Random) -> dict[str, float]:
    if rng.random() < EPSILON:
        return {a.hypothesis_id: rng.random() for a in arms}
    out: dict[str, float] = {}
    for a in arms:
        mean = (a.ucb_sum / a.ucb_n) if a.ucb_n > 0 else 0.5
        out[a.hypothesis_id] = mean
    return out


def uniform_scores(arms: list[Arm], rng: random.Random) -> dict[str, float]:
    return {a.hypothesis_id: rng.random() for a in arms}


# ---- hybrid orchestration --------------------------------------------------

def choose_policy(rng: random.Random) -> Policy:
    r = rng.random()
    acc = 0.0
    for name, w in POLICY_WEIGHTS.items():
        acc += w
        if r < acc:
            return name  # type: ignore[return-value]
    return "thompson"


def _normalize(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0:
        n = len(weights)
        return {k: 1.0 / n for k in weights} if n else {}
    return {k: v / total for k, v in weights.items()}


def _allocate_from_scores(arms: list[Arm], scores: dict[str, float]) -> dict[str, float]:
    """Convert per-arm scores into bankroll fractions using the 50/40/floor rule."""
    if not arms:
        return {}
    by_id = {a.hypothesis_id: a for a in arms}
    eligible = [aid for aid in scores if scores[aid] != float("-inf")]
    if not eligible:
        return {a.hypothesis_id: 0.0 for a in arms}

    # Inf scores (untried UCB1 arms) all tie for the top.
    inf_ids = [aid for aid in eligible if scores[aid] == float("inf")]
    if inf_ids:
        top_ids = inf_ids
    else:
        max_score = max(scores[aid] for aid in eligible)
        top_ids = [aid for aid in eligible if scores[aid] == max_score]

    raw: dict[str, float] = {aid: 0.0 for aid in scores}

    # Top share split among tied leaders.
    top_each = TOP_SHARE / len(top_ids)
    for aid in top_ids:
        raw[aid] += top_each

    # Above-median group (excluding leaders, excluding inf).
    finite_scores = [scores[aid] for aid in eligible if scores[aid] != float("inf")]
    if finite_scores:
        median = sorted(finite_scores)[len(finite_scores) // 2]
        above = [aid for aid in eligible if aid not in top_ids and scores[aid] >= median]
        if above:
            each = ABOVE_MEDIAN_SHARE / len(above)
            for aid in above:
                raw[aid] += each

    # TESTING floor.
    for aid, a in by_id.items():
        if a.status == "testing" and raw[aid] < TESTING_FLOOR:
            raw[aid] = TESTING_FLOOR

    # Killed / refuted arms get zero.
    for aid, a in by_id.items():
        if a.status in ("refuted", "killed"):
            raw[aid] = 0.0

    return _normalize(raw)


def allocate(
    arms: Iterable[Arm],
    rng: random.Random | None = None,
    policy: Policy | None = None,
) -> Allocation:
    """Run one bandit tick across the given arms."""
    rng = rng or random.Random()
    arms_list = list(arms)
    if not arms_list:
        return Allocation(
            tick_id=str(uuid.uuid4()),
            ts=_now_iso(),
            policy="uniform",
            allocations={},
            rationale="no arms",
        )

    chosen: Policy = policy or choose_policy(rng)
    if chosen == "thompson":
        scores = thompson_sample(arms_list, rng)
    elif chosen == "ucb1":
        scores = ucb1_scores(arms_list)
    elif chosen == "epsilon_greedy":
        scores = epsilon_greedy_scores(arms_list, rng)
    else:
        scores = uniform_scores(arms_list, rng)

    allocations = _allocate_from_scores(arms_list, scores)

    top = max(allocations, key=lambda k: allocations[k]) if allocations else "—"
    rationale = f"policy={chosen} top={top} alloc_sum={sum(allocations.values()):.3f}"
    return Allocation(
        tick_id=str(uuid.uuid4()),
        ts=_now_iso(),
        policy=chosen,
        allocations=allocations,
        rationale=rationale,
    )


def update_posterior(arm: Arm, beat_crowd: bool, reward: float | None = None) -> Arm:
    """Return a new Arm with α/β and UCB stats updated.

    ``beat_crowd`` flips Beta-Bernoulli. ``reward`` (in [0, 1]) feeds UCB1
    running mean; if None, falls back to 1.0 when beat_crowd else 0.0.
    """
    r = reward if reward is not None else (1.0 if beat_crowd else 0.0)
    r = max(0.0, min(1.0, r))
    return Arm(
        hypothesis_id=arm.hypothesis_id,
        alpha=arm.alpha + (1.0 if beat_crowd else 0.0),
        beta=arm.beta + (0.0 if beat_crowd else 1.0),
        ucb_n=arm.ucb_n + 1,
        ucb_sum=arm.ucb_sum + r,
        status=arm.status,
    )
