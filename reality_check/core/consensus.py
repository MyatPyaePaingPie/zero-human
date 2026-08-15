"""Cross-strategy DARWINIAN consensus.

When multiple strategies fire on the same market, we want one trade
decision, not N conflicting ones. This module aggregates per-market
forecasts and returns a single ``ConsensusVerdict``.

The crystal-os DARWINIAN mode is the conceptual ancestor (nodes vote,
dissenters get penalized), but for trading we keep it light: pure
majority on ``side``, average ``p`` across agreeing voters, ``dissent_score``
measures how far disagreeing voters are from the agreed price.

Skip rule: ``side = skip`` whenever the dissent_score exceeds
``DISSENT_THRESHOLD`` — disagreement means uncertainty.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from reality_check.core.models import Forecast

Side = Literal["yes", "no", "skip"]

DISSENT_THRESHOLD = 0.20  # if min(p_for) - max(p_against) < this, skip


@dataclass(frozen=True)
class Vote:
    hypothesis_id: str
    forecast: Forecast


@dataclass(frozen=True)
class ConsensusVerdict:
    side: Side
    agreed_p: float
    agreed_confidence: float
    voters_for: tuple[str, ...]
    voters_against: tuple[str, ...]
    voters_skip: tuple[str, ...]
    dissent_score: float
    rationale: str


def _agreement_p(votes: list[Vote], side: Side) -> float:
    matched = [v.forecast.p for v in votes if v.forecast.side == side]
    if not matched:
        return 0.5
    return sum(matched) / len(matched)


def _agreement_confidence(votes: list[Vote], side: Side) -> float:
    matched = [v.forecast.confidence for v in votes if v.forecast.side == side]
    if not matched:
        return 0.0
    return sum(matched) / len(matched)


def evaluate(votes: Iterable[Vote]) -> ConsensusVerdict:
    """Aggregate per-market votes into a single verdict.

    Algorithm:
      1. Count sides voted (excluding skip).
      2. If no non-skip votes -> skip.
      3. If there's a tie among non-skip sides -> skip.
      4. Otherwise take the majority side. Compute dissent_score as
         the gap between agreed mean p and the opposing-side mean p.
      5. If dissent_score < DISSENT_THRESHOLD -> downgrade to skip.
    """
    votes_list = [v for v in votes]
    if not votes_list:
        return ConsensusVerdict("skip", 0.5, 0.0, (), (), (), 0.0, "no votes")

    skips = [v.hypothesis_id for v in votes_list if v.forecast.side == "skip"]
    actives = [v for v in votes_list if v.forecast.side in ("yes", "no")]
    if not actives:
        return ConsensusVerdict("skip", 0.5, 0.0, (), (), tuple(skips), 0.0, "all skipped")

    counter = Counter(v.forecast.side for v in actives)
    top_side, top_count = counter.most_common(1)[0]
    runner_up = counter.most_common(2)[1] if len(counter) > 1 else None

    if runner_up and runner_up[1] == top_count:
        return ConsensusVerdict(
            "skip", 0.5, 0.0,
            tuple(v.hypothesis_id for v in actives if v.forecast.side == "yes"),
            tuple(v.hypothesis_id for v in actives if v.forecast.side == "no"),
            tuple(skips), 0.0, "tied vote",
        )

    side: Side = top_side  # type: ignore[assignment]
    against_side = "no" if side == "yes" else "yes"

    voters_for = tuple(v.hypothesis_id for v in actives if v.forecast.side == side)
    voters_against = tuple(v.hypothesis_id for v in actives if v.forecast.side == against_side)

    agreed_p = _agreement_p(actives, side)
    agreed_c = _agreement_confidence(actives, side)
    against_p = _agreement_p(actives, against_side)
    dissent_score = abs(agreed_p - against_p) if voters_against else 0.0

    if voters_against and dissent_score < DISSENT_THRESHOLD:
        return ConsensusVerdict(
            "skip", agreed_p, agreed_c, voters_for, voters_against, tuple(skips),
            dissent_score,
            f"dissent {dissent_score:.2f} < {DISSENT_THRESHOLD}",
        )

    return ConsensusVerdict(
        side, agreed_p, agreed_c, voters_for, voters_against, tuple(skips),
        dissent_score,
        f"majority {side} by {top_count}/{len(actives)}, p={agreed_p:.2f}, dissent={dissent_score:.2f}",
    )
