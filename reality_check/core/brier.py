"""Brier score + calibration diagnostics.

Brier(p, y) = (p - y)^2  for y in {0, 1}. Lower is better. The "edge" we
want vs the crowd is ``brier_delta = crowd_brier - strategy_brier >= 0.010``.
"""
from __future__ import annotations

from dataclasses import dataclass


def brier(p: float, outcome: float) -> float:
    """Squared error of a probabilistic forecast."""
    return (p - outcome) ** 2


def brier_score(pairs: list[tuple[float, float]]) -> float:
    """Mean Brier across (forecast, outcome) pairs."""
    if not pairs:
        return float("nan")
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs)


def brier_delta(strategy: list[tuple[float, float]], crowd: list[tuple[float, float]]) -> float:
    """crowd_brier - strategy_brier. Positive means strategy is better-calibrated."""
    return brier_score(crowd) - brier_score(strategy)


@dataclass(frozen=True)
class DecileBin:
    lower: float
    upper: float
    n: int
    avg_forecast: float
    avg_outcome: float

    @property
    def deviation(self) -> float:
        return abs(self.avg_forecast - self.avg_outcome)


def calibration_deciles(pairs: list[tuple[float, float]]) -> list[DecileBin]:
    """Bin forecasts into 10 equal-width buckets; compute observed frequency per bucket.

    Empty bins are returned with n=0 so callers can detect coverage gaps.
    """
    bins: list[list[tuple[float, float]]] = [[] for _ in range(10)]
    for p, y in pairs:
        idx = min(int(p * 10), 9)
        bins[idx].append((p, y))
    out: list[DecileBin] = []
    for i, bucket in enumerate(bins):
        lower = i / 10.0
        upper = (i + 1) / 10.0
        if not bucket:
            out.append(DecileBin(lower, upper, 0, (lower + upper) / 2.0, float("nan")))
            continue
        n = len(bucket)
        avg_p = sum(p for p, _ in bucket) / n
        avg_y = sum(y for _, y in bucket) / n
        out.append(DecileBin(lower, upper, n, avg_p, avg_y))
    return out


def max_calibration_deviation(pairs: list[tuple[float, float]]) -> float:
    """Worst-case |forecast - observed| across non-empty deciles."""
    devs = [b.deviation for b in calibration_deciles(pairs) if b.n > 0]
    return max(devs) if devs else float("nan")
