"""Learn from receipts: arm gain, evaluator reputation, and the swarm check.

Every number here is rebuilt from settled jobs in the store on each call (money-swarm lineage
rule: continuity belongs to the files, never to an in-memory object). Nothing is asserted;
everything is measured against the human oracle and reported with its n.

augur lessons baked in:
- one job counts once (correlated re-logs inflated augur's n by ~165x and lit a false badge)
- gain is RELATIVE to the free baseline (the internal ensemble), never absolute
- fail closed: below MIN_SETTLED an arm keeps its prior and says so

Definitions (per settled job with n_humans >= HUMAN_MIN_N_TO_SETTLE):
- baseline error  = brier(ensemble p, human majority) averaged over claims
- arm gain        = 1 - mean(brier of ensemble AFTER humans, which is 0 by construction) ... no.
  We cannot observe "the buyer's decision after judgment" here, so gain is measured as the
  fraction of jobs where the humans OVERTURNED the ensemble on at least one claim, weighted by
  how wrong the ensemble was (brier). Interpretation: the share of internal error that buying
  this arm removed. Honest and cheap; stated as such in `reason`.
- evaluator reputation = mean brier vs humans per persona id (lower is better), n claims
- swarm check = ensemble brier vs best single evaluator vs median single evaluator vs worst,
  per job and cumulative. brier_delta > 0 means the swarm beat the single agent (augur sign).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from statistics import mean, median

from reality_check import store
from reality_check.core import voi
from reality_check.core.brier import brier

MIN_SETTLED = voi.MIN_SETTLED


@dataclass
class ArmStat:
    arm: str
    n_settled: int = 0
    overturned_jobs: int = 0
    measured_gain: float | None = None
    baseline_brier: float | None = None
    live: bool = False  # True once n_settled >= MIN_SETTLED and the gate uses the measurement


@dataclass
class EvaluatorStat:
    evaluator: str
    n_claims: int = 0
    mean_brier: float | None = None
    overturned_share: float | None = None


@dataclass
class SwarmCheck:
    n_jobs: int = 0
    ensemble_brier: float | None = None
    best_single_brier: float | None = None
    median_single_brier: float | None = None
    worst_single_brier: float | None = None
    delta_vs_median_single: float | None = None   # >0: swarm helped
    delta_vs_best_single: float | None = None     # >0: swarm beat even the best lone agent
    ensemble_cost_usd: float = 0.0
    single_cost_usd: float = 0.0
    verdict: str = "unmeasured"
    per_job: list[dict] = field(default_factory=list)


def _settled_jobs() -> list[dict]:
    out = []
    for j in store.list_jobs(limit=5000):
        if j["status"] != "settled":
            continue
        st = j.get("state") or {}
        if not any("humans" in c for c in st.get("claims", [])):
            continue
        out.append(j)
    return out


def _outcome(c: dict) -> float | None:
    h = c.get("humans") or {}
    return 1.0 if h.get("side") == "yes" else 0.0 if h.get("side") == "no" else None


def arm_stats() -> dict[str, ArmStat]:
    stats = {a.name: ArmStat(a.name) for a in voi.DEFAULT_ARMS}
    seen: set[str] = set()
    per_arm_briers: dict[str, list[float]] = {}
    per_arm_weighted: dict[str, list[float]] = {}
    for j in _settled_jobs():
        if j["job_id"] in seen:
            continue
        seen.add(j["job_id"])
        arm = ((j["state"].get("voi") or {}).get("arm")) or None
        if not arm or arm not in stats:
            continue
        s = stats[arm]
        s.n_settled += 1
        briers, flips = [], 0
        for c in j["state"].get("claims", []):
            o = _outcome(c)
            if o is None:
                continue
            b = brier(c["consensus"]["p"], o)
            briers.append(b)
            flips += int(bool(c["consensus"].get("humans_flipped_verdict")))
        if flips:
            s.overturned_jobs += 1
        if briers:
            per_arm_briers.setdefault(arm, []).append(mean(briers))
            # weight: an overturned job with high internal error = large removed error
            per_arm_weighted.setdefault(arm, []).append(mean(briers) if flips else 0.0)
    for arm, s in stats.items():
        if s.n_settled:
            s.baseline_brier = round(mean(per_arm_briers.get(arm, [0.0])), 4)
            base = mean(per_arm_briers.get(arm, [0.0]))
            removed = mean(per_arm_weighted.get(arm, [0.0]))
            s.measured_gain = round(min(1.0, removed / base), 4) if base > 0 else 0.0
            s.live = s.n_settled >= MIN_SETTLED
    return stats


def arms() -> tuple[voi.EvidenceArm, ...]:
    """DEFAULT_ARMS with measured gains attached. Feed to voi.decide(arms=...). Never raises."""
    try:
        st = arm_stats()
        return tuple(
            voi.EvidenceArm(a.name, a.price_usd, a.latency_s, a.prior_gain,
                            measured_gain=st[a.name].measured_gain, n_settled=st[a.name].n_settled)
            for a in voi.DEFAULT_ARMS)
    except Exception:
        return voi.DEFAULT_ARMS


def evaluator_stats() -> dict[str, EvaluatorStat]:
    stats: dict[str, EvaluatorStat] = {}
    acc: dict[str, list[float]] = {}
    flips: dict[str, list[int]] = {}
    for j in _settled_jobs():
        for c in j["state"].get("claims", []):
            o = _outcome(c)
            if o is None:
                continue
            for e in c.get("evaluators", []):
                if e.get("side") == "skip":
                    continue
                eid = e["id"]
                acc.setdefault(eid, []).append(brier(e["p"], o))
                flips.setdefault(eid, []).append(int((e["p"] > 0.5) != (o == 1.0)))
    for eid, bs in acc.items():
        stats[eid] = EvaluatorStat(eid, len(bs), round(mean(bs), 4), round(mean(flips[eid]), 3))
    return stats


def swarm_check() -> SwarmCheck:
    """Does collaboration help, or just add latency and cost? Ensemble vs lone evaluator, scored
    against humans. Uses only jobs where >=2 non-skip evaluators voted on a settled claim."""
    sc = SwarmCheck()
    ens, best, med, worst = [], [], [], []
    for j in _settled_jobs():
        job_e, job_b, job_m, job_w = [], [], [], []
        for c in j["state"].get("claims", []):
            o = _outcome(c)
            if o is None:
                continue
            singles = [brier(e["p"], o) for e in c.get("evaluators", []) if e.get("side") != "skip"]
            if len(singles) < 2:
                continue
            job_e.append(brier(c["consensus"]["p"], o))
            job_b.append(min(singles)); job_m.append(median(singles)); job_w.append(max(singles))
        if not job_e:
            continue
        e_, b_, m_, w_ = mean(job_e), mean(job_b), mean(job_m), mean(job_w)
        ens.append(e_); best.append(b_); med.append(m_); worst.append(w_)
        sc.per_job.append({"job_id": j["job_id"], "ensemble": round(e_, 4), "best_single": round(b_, 4),
                           "median_single": round(m_, 4), "worst_single": round(w_, 4),
                           "swarm_helped_vs_median": e_ < m_})
    sc.n_jobs = len(ens)
    if not ens:
        return sc
    sc.ensemble_brier = round(mean(ens), 4)
    sc.best_single_brier = round(mean(best), 4)
    sc.median_single_brier = round(mean(med), 4)
    sc.worst_single_brier = round(mean(worst), 4)
    sc.delta_vs_median_single = round(sc.median_single_brier - sc.ensemble_brier, 4)
    sc.delta_vs_best_single = round(sc.best_single_brier - sc.ensemble_brier, 4)
    # cost: ensemble cost from ledger; a single evaluator is ~1/N of it
    with store.conn() as c:
        row = c.execute("SELECT COALESCE(SUM(amount_usd),0) s FROM ledger WHERE kind='cost.ensemble'").fetchone()
    sc.ensemble_cost_usd = round(float(row["s"]), 4)
    n_eval = max(1, max((len(c.get("evaluators", [])) for j in _settled_jobs() for c in j["state"].get("claims", [])), default=1))
    sc.single_cost_usd = round(sc.ensemble_cost_usd / n_eval, 4)
    if sc.n_jobs < 3:
        sc.verdict = f"unmeasured (n={sc.n_jobs} < 3)"
    elif sc.delta_vs_best_single > 0:
        sc.verdict = "swarm beat even the best lone agent"
    elif sc.delta_vs_median_single > 0:
        sc.verdict = "swarm beat a typical lone agent, not the best one"
    else:
        sc.verdict = "swarm did NOT beat a lone agent; it added cost and latency"
    return sc


def report() -> dict:
    """Everything the dashboard shows. Never raises."""
    try:
        return {
            "arms": {k: asdict(v) for k, v in arm_stats().items()},
            "evaluators": {k: asdict(v) for k, v in evaluator_stats().items()},
            "swarm_check": asdict(swarm_check()),
            "min_settled": MIN_SETTLED,
        }
    except Exception as exc:
        return {"error": str(exc), "arms": {}, "evaluators": {}, "swarm_check": asdict(SwarmCheck())}
