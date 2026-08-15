"""The judgment loop, rubric-shaped: a job = N binary claims.

Per claim: evaluators -> consensus -> per-claim verdict. Job level: VOI on the worst-agreed
claim decides whether humans get bought; humans answer every claim on one page; settlement
scores each evaluator per claim against the human majority (augur brier pattern).

Status machine per job:
  evaluating -> settled                      (VOI: internal consensus is enough)
  evaluating -> awaiting_humans -> settled   (VOI bought a human panel; humans answer via /rate)
"""
from __future__ import annotations

import uuid

from reality_check import evaluators, panels, skus, store
from reality_check.core import consensus, voi
from reality_check.core.brier import brier
from reality_check.core.models import ClaimVerdict, JudgeRequest, Verdict, VoiDecision

HUMAN_TARGET_N = 5
HUMAN_MIN_N_TO_SETTLE = 3


def _majority(yes: int, no: int) -> tuple[str, float]:
    total = yes + no
    if total == 0:
        return "undecided", 0.5
    return ("yes" if yes > no else "no" if no > yes else "undecided"), yes / total


def _judge_claim(idx: int, claim: str, text: str, personas: list[str] | None) -> tuple[dict, float]:
    ev = evaluators.evaluate(claim, text, personas)
    cv = consensus.evaluate(ev.votes)
    p_internal = cv.agreed_p if cv.side != "skip" else 0.5
    n_active = len(cv.voters_for) + len(cv.voters_against)
    agreement = len(cv.voters_for) / n_active if n_active else 0.0
    dissent = max(0.0, min(1.0, (1.0 - agreement) + (0.5 if cv.side == "skip" else 0.0)))
    return {
        "idx": idx, "claim": claim,
        "evaluators": [{"id": v.hypothesis_id, "p": v.forecast.p, "confidence": v.forecast.confidence,
                        "reasoning": v.forecast.reasoning, "refuted_by": v.forecast.refuted_by, "side": v.forecast.side}
                       for v in ev.votes],
        "consensus": {"side": cv.side, "p": p_internal, "agreement": agreement, "dissent": dissent, "rationale": cv.rationale},
        "provider": ev.provider,
    }, ev.cost_usd


def start(req: JudgeRequest, *, paid_usd: float = 0.0, job_id: str | None = None) -> Verdict:
    job_id = job_id or uuid.uuid4().hex[:12]
    store.put_job(job_id, req.buyer_id, "evaluating", req.model_dump(), {})
    store.event(job_id, "job.created", {"sku": req.sku, "claims": req.claims, "buyer": req.buyer_id})
    if paid_usd > 0:
        store.ledger_add(job_id, "revenue", paid_usd, f"{req.sku} sold")

    personas = req.personas or skus.default_personas(req.sku)
    claims, cost = [], 0.0
    for i, claim in enumerate(req.claims):
        c, cst = _judge_claim(i, claim, req.input, personas)
        claims.append(c)
        cost += cst
    if cost:
        store.ledger_add(job_id, "cost.ensemble", cost, claims[0]["provider"])
    worst = max(claims, key=lambda c: c["consensus"]["dissent"])
    store.event(job_id, "evaluators.done", {"claims": [(c["consensus"]["side"], round(c["consensus"]["p"], 2), round(c["consensus"]["dissent"], 2)) for c in claims], "cost": cost})

    decision = voi.decide(
        p_internal=worst["consensus"]["p"], dissent=worst["consensus"]["dissent"],
        cost_if_wrong_usd=req.cost_if_wrong_usd, max_budget_usd=req.max_budget_usd,
    )
    if req.force_humans and not decision.buy:
        decision = decision.model_copy(update={"buy": True, "arm": decision.arm or "linq_panel",
                                               "reason": "humans sold to buyer (force_humans); VOI gate bypassed: " + decision.reason})
    store.event(job_id, "voi.decided", decision.model_dump())

    state = {"claims": claims, "voi": decision.model_dump(), "panel": None,
             "human_question": req.human_question or skus.default_human_question(req.sku)}
    if decision.buy and decision.arm:
        panel = panels.for_arm(decision.arm)
        handle = panel.launch(job_id, state["human_question"] or req.claims[0], req.input, HUMAN_TARGET_N)
        state["panel"] = handle.__dict__
        if handle.price_usd:
            store.ledger_add(job_id, f"cost.{handle.source}", handle.price_usd, f"panel n={handle.n_requested}")
        store.event(job_id, "panel.launched", state["panel"])
        store.put_job(job_id, req.buyer_id, "awaiting_humans", req.model_dump(), state)
    else:
        store.put_job(job_id, req.buyer_id, "settled", req.model_dump(), state)
        store.event(job_id, "job.settled", {"via": "internal"})
    return verdict(job_id)


def _answers_by_claim(job_id: str) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for a in store.human_answers(job_id):
        if a["answer_yes"] is not None:
            out.setdefault(a["claim_idx"], []).append(a)
    return out


def on_human_answer(job_id: str) -> Verdict:
    """Called after every human submission; settles once enough humans answered claim 0."""
    job = store.get_job(job_id)
    if not job or job["status"] == "settled":
        return verdict(job_id)
    by_claim = _answers_by_claim(job_id)
    if len(by_claim.get(0, [])) >= HUMAN_MIN_N_TO_SETTLE:
        _settle_against_humans(job, by_claim)
    return verdict(job_id)


def _settle_against_humans(job: dict, by_claim: dict[int, list[dict]]) -> None:
    state = job["state"]
    flipped = 0
    for c in state["claims"]:
        answers = by_claim.get(c["idx"], [])
        yes = sum(1 for a in answers if a["answer_yes"])
        side, p_h = _majority(yes, len(answers) - yes)
        c["humans"] = {"yes": yes, "no": len(answers) - yes, "p": p_h, "side": side}
        outcome = 1.0 if side == "yes" else 0.0 if side == "no" else None
        if outcome is None:
            continue
        for e in c["evaluators"]:
            e["brier_vs_humans"] = round(brier(e["p"], outcome), 4)
        c["consensus"]["brier_vs_humans"] = round(brier(c["consensus"]["p"], outcome), 4)
        c["consensus"]["humans_flipped_verdict"] = c["consensus"]["side"] != side
        flipped += int(c["consensus"]["humans_flipped_verdict"])
    state["humans_flipped_claims"] = flipped
    store.put_job(job["job_id"], job["buyer_id"], "settled", job["request"], state)
    store.event(job["job_id"], "job.settled", {"via": "humans", "flipped_claims": flipped, "n_humans": len(by_claim.get(0, []))})


def _claim_verdict(c: dict, answers: list[dict]) -> ClaimVerdict:
    cons = c["consensus"]
    if answers:
        yes = sum(1 for a in answers if a["answer_yes"])
        side, p_h = _majority(yes, len(answers) - yes)
        agreement = max(p_h, 1 - p_h) if side != "undecided" else 0.5
        minority = next((a["free_text"] for a in answers if bool(a["answer_yes"]) != (side == "yes") and a["free_text"]), "")
        return ClaimVerdict(claim=c["claim"], verdict=side, p_internal=round(cons["p"], 3), agreement=round(agreement, 3),
                            p_humans=round(p_h, 3), n_humans=len(answers), minority_view=minority[:400])
    side = cons["side"] if cons["side"] in ("yes", "no") else "undecided"
    against = [e for e in c["evaluators"] if e["side"] not in (side, "skip")]
    return ClaimVerdict(claim=c["claim"], verdict=side, p_internal=round(cons["p"], 3), agreement=round(cons["agreement"], 3),
                        minority_view=(against[0]["reasoning"] if against else "")[:400])


def verdict(job_id: str) -> Verdict:
    job = store.get_job(job_id)
    if not job:
        raise KeyError(job_id)
    st = job["state"]
    by_claim = _answers_by_claim(job_id)
    cvs = [_claim_verdict(c, by_claim.get(c["idx"], [])) for c in st.get("claims", [])]
    n_humans = len(by_claim.get(0, []))
    if not cvs:
        return Verdict(job_id=job_id, status=job["status"], verdict="undecided", p=0.5, confidence=0.0, agreement=0.0,
                       n_evaluators=0, n_humans=0, summary="evaluating", minority_view="")
    all_skipped = all(e["side"] == "skip" for c in st.get("claims", []) for e in c["evaluators"])
    passed = sum(1 for v in cvs if v.verdict == "yes")
    overall = "yes" if passed == len(cvs) else "no" if any(v.verdict == "no" for v in cvs) else "undecided"
    p = sum(v.p_humans if v.p_humans is not None else v.p_internal for v in cvs) / len(cvs)
    agreement = sum(v.agreement for v in cvs) / len(cvs)
    flipped = st.get("humans_flipped_claims")
    if n_humans:
        summary = f"{passed}/{len(cvs)} claims hold per {n_humans} humans. " + (
            f"Humans overturned the models on {flipped} claim(s)." if flipped else "Humans agree with the models.")
    else:
        summary = f"{passed}/{len(cvs)} claims hold per model consensus. " + (
            "Human panel pending." if job["status"] == "awaiting_humans" else "Internal consensus sufficient.")
    if all_skipped:
        summary = "Model evaluators unavailable (provider errors); humans are the only evidence. " + summary
    minority = next((v.minority_view for v in cvs if v.minority_view), "")
    tot = _job_money(job_id)
    n_eval = len(st["claims"][0]["evaluators"]) if st.get("claims") else 0
    all_answers = store.human_answers(job_id)
    return Verdict(
        job_id=job_id, status=job["status"], verdict=overall, p=round(p, 3),
        confidence=round(agreement * (1.0 if n_humans else 0.6), 3), agreement=round(agreement, 3),
        n_evaluators=n_eval, n_humans=n_humans, summary=summary, minority_view=minority, claims=cvs,
        voi=VoiDecision(**st["voi"]) if st.get("voi") else None,
        human_answers=[{"claim": a["claim_idx"], "yes": a["answer_yes"], "text": a["free_text"], "src": a["source"]} for a in all_answers],
        revenue_usd=tot["revenue"], evidence_cost_usd=tot["cost"], margin_usd=tot["revenue"] - tot["cost"],
    )


def _job_money(job_id: str) -> dict:
    with store.conn() as c:
        rows = c.execute("SELECT kind, SUM(amount_usd) s FROM ledger WHERE job_id=? GROUP BY kind", (job_id,)).fetchall()
    rev = sum(r["s"] for r in rows if r["kind"] == "revenue")
    cost = sum(r["s"] for r in rows if r["kind"].startswith("cost"))
    return {"revenue": rev, "cost": cost}
