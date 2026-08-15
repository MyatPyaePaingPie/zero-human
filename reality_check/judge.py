"""The judgment loop, rubric-shaped: a job = N binary claims.

Per claim: evaluators -> consensus -> per-claim verdict. Job level: VOI on the worst-agreed
claim decides whether humans get bought; humans answer every claim on one page; settlement
scores each evaluator per claim against the human majority (augur brier pattern).

Status machine per job:
  evaluating -> settled                      (VOI: internal consensus is enough)
  evaluating -> awaiting_humans -> settled   (VOI bought a human panel; humans answer via /rate)
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from reality_check import evaluators, linq_client, panels, replay_client, skus, store
from reality_check.core import consensus, voi
from reality_check.core.brier import brier
from reality_check.core.models import ClaimVerdict, JudgeRequest, Verdict, VoiDecision
from reality_check.policy import envelope, learning

HUMAN_TARGET_N = 5
HUMAN_MIN_N_TO_SETTLE = 3
HUMAN_TIMEOUT_S = float(os.environ.get("RC_HUMAN_TIMEOUT_S", "1800"))  # after this, settle with what exists


def seconds_to_deadline() -> float | None:
    """RC_DEADLINE_ISO (e.g. 2026-08-15T18:30:00-07:00): evidence that cannot arrive before it
    is not worth buying. None when unset."""
    raw = os.environ.get("RC_DEADLINE_ISO")
    if not raw:
        return None
    try:
        dl = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dl.tzinfo is None:
        dl = dl.replace(tzinfo=timezone.utc)
    return max(0.0, (dl - datetime.now(timezone.utc)).total_seconds())


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


HUMAN_ARMS = ("linq_panel", "terac_general", "terac_expert")   # recruiting arms, cheapest first
# "local_panel" (free in-room rate page, no recruiting) is not routable by VOI: it is only the
# explicit deadline fallback below and the envelope-denied fallback in start().
EXPERT_ARMS = ("terac_expert",)


def _apply_standard(standard: str, decision, arms, max_budget_usd: float, max_latency_s: float | None):
    """The evidence standard is a FLOOR, not an arm choice. VOI math still ran (and is shown);
    if its pick does not satisfy the floor, choose the cheapest arm that does, within deadline.
    Budget is not a reason to sell an unbacked verdict: the free local page satisfies human_backed."""
    if standard == "voi_routed":
        return decision
    need = EXPERT_ARMS if standard == "expert_backed" else HUMAN_ARMS
    if decision.buy and decision.arm in need:
        return decision.model_copy(update={"reason": f"standard {standard} satisfied by VOI pick: " + decision.reason})
    by_name = {a.name: a for a in arms}
    for name in need:
        a = by_name.get(name)
        if a and (max_latency_s is None or a.latency_s <= max_latency_s):
            return decision.model_copy(update={"buy": True, "arm": name,
                                               "reason": f"standard {standard} requires humans; cheapest satisfying arm = {name} ${a.price_usd:.2f}; VOI alone said: " + decision.reason})
    return decision.model_copy(update={"buy": True, "arm": "local_panel",
                                       "reason": f"standard {standard}: no recruiting arm can return before the deadline; free local page (local_panel); VOI alone said: " + decision.reason})


def start(req: JudgeRequest, *, paid_usd: float = 0.0, job_id: str | None = None) -> Verdict:
    job_id = job_id or uuid.uuid4().hex[:12]
    store.put_job(job_id, req.buyer_id, "evaluating", req.model_dump(), {})
    store.event(job_id, "job.created", {"sku": req.sku, "claims": req.claims, "buyer": req.buyer_id})
    if paid_usd > 0:
        store.ledger_add_once(job_id, "revenue", paid_usd, f"{req.sku} sold")

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

    max_latency = seconds_to_deadline()
    arms = learning.arms()  # measured gains from settled jobs flow into the gate
    decision = voi.decide(
        p_internal=worst["consensus"]["p"], dissent=worst["consensus"]["dissent"],
        cost_if_wrong_usd=req.cost_if_wrong_usd, max_budget_usd=req.max_budget_usd,
        arms=arms, max_latency_s=max_latency,
    )
    if max_latency is not None:
        decision = decision.model_copy(update={"reason": decision.reason + f" (deadline in {max_latency/60:.0f} min)"})
    decision = _apply_standard(req.evidence_standard or "voi_routed", decision, arms, req.max_budget_usd, max_latency)
    use_free_panel = False
    if decision.buy and decision.arm:
        # company spend authority is code (envelope), never the buyer's flag or free text
        price = next((a.price_usd for a in arms if a.name == decision.arm), 0.0)
        if not envelope.gate_panel_launch(job_id, decision.arm, price, paid_usd):
            if req.force_humans:
                # humans were sold: fall to the free in-room page rather than no humans
                use_free_panel = True
                decision = decision.model_copy(update={"reason": "envelope denied paid arm; humans via free local page: " + decision.reason})
            else:
                decision = decision.model_copy(update={"buy": False, "reason": "envelope denied (see envelope.checked event): " + decision.reason})
    store.event(job_id, "voi.decided", decision.model_dump())

    state = {"claims": claims, "voi": decision.model_dump(), "panel": None,
             "human_question": req.human_question or skus.default_human_question(req.sku)}
    if decision.buy and decision.arm:
        panel = panels.REGISTRY["local"] if use_free_panel else panels.for_arm(decision.arm)
        approve = lambda quoted, arm=decision.arm: envelope.gate_panel_launch(job_id, arm, quoted, paid_usd)  # noqa: E731
        handle = panel.launch(job_id, state["human_question"] or req.claims[0], req.input, HUMAN_TARGET_N, approve=approve)
        if handle.source != "local" and handle.external_id is None:
            # paid backend recruited nobody (dry, HTTP error, gate refused quote): do not stall the buyer
            store.event(job_id, "panel.fallback", {"from": handle.source, "to": "local", "rate_url": handle.rate_url})
            handle = panels.REGISTRY["local"].launch(job_id, state["human_question"] or req.claims[0], req.input, HUMAN_TARGET_N)
        state["panel"] = handle.__dict__
        state["launched_at"] = store.now()
        # learning attributes outcomes to the arm that actually recruited, not the one VOI named
        state["arm_used"] = {"local": "local_panel", "linq": "linq_panel", "terac": decision.arm if decision.arm.startswith("terac") else "terac_general"}.get(handle.source, handle.source)
        if handle.price_usd:
            store.ledger_add(job_id, f"cost.{handle.source}", handle.price_usd, f"panel n={handle.n_requested}")
        store.event(job_id, "panel.launched", state["panel"])
        store.put_job(job_id, req.buyer_id, "awaiting_humans", req.model_dump(), state)
    else:
        store.put_job(job_id, req.buyer_id, "settled", req.model_dump(), state)
        store.event(job_id, "job.settled", {"via": "internal"})
        _notify(job_id)
    return verdict(job_id)


def _notify(job_id: str) -> None:
    """Text the buyer once per job when it settles (Linq), if they asked."""
    job = store.get_job(job_id)
    phone = (job or {}).get("request", {}).get("notify_phone")
    if not phone or (job["state"] or {}).get("notified"):
        return
    v = verdict(job_id)
    linq_client.notify_verdict(job_id, phone, f"{v.verdict} (p={v.p:.2f}, {v.n_humans} humans). {v.summary[:120]}")
    job["state"]["notified"] = True
    store.put_job(job_id, job["buyer_id"], job["status"], job["request"], job["state"])


def _answers_by_claim(job_id: str) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for a in store.human_answers(job_id):
        if a["answer_yes"] is not None:
            out.setdefault(a["claim_idx"], []).append(a)
    return out


def on_human_answer(job_id: str) -> Verdict:
    """Called after every human submission. Settles at HUMAN_MIN_N_TO_SETTLE and re-settles on
    every answer up to HUMAN_TARGET_N so brier/flipped track the same majority verdict() shows;
    frozen once the target is reached."""
    job = store.get_job(job_id)
    if not job:
        return verdict(job_id)
    by_claim = _answers_by_claim(job_id)
    n = len(by_claim.get(0, []))
    if job["status"] == "settled" and (n > HUMAN_TARGET_N or job["state"].get("settled_n_humans", 0) >= HUMAN_TARGET_N):
        return verdict(job_id)
    if n >= HUMAN_MIN_N_TO_SETTLE:
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
    state["settled_n_humans"] = len(by_claim.get(0, []))
    store.put_job(job["job_id"], job["buyer_id"], "settled", job["request"], state)
    store.event(job["job_id"], "job.settled", {"via": "humans", "flipped_claims": flipped, "n_humans": len(by_claim.get(0, []))})
    _notify(job["job_id"])


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


def _timed_out(job: dict) -> bool:
    la = job["state"].get("launched_at")
    if job["status"] != "awaiting_humans" or not la:
        return False
    try:
        t0 = datetime.fromisoformat(la)
    except ValueError:
        return False
    if t0.tzinfo is None:
        t0 = t0.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - t0).total_seconds() > HUMAN_TIMEOUT_S


def settle_on_timeout(job_id: str) -> bool:
    """awaiting_humans past RC_HUMAN_TIMEOUT_S: settle with the humans that exist (>=1) or
    model-only, and say so. Returns True if it settled."""
    job = store.get_job(job_id)
    if not job or not _timed_out(job):
        return False
    by_claim = _answers_by_claim(job_id)
    if by_claim.get(0):
        _settle_against_humans(job, by_claim)
        via = f"timeout with {len(by_claim[0])} humans"
    else:
        job["state"]["timed_out"] = True
        store.put_job(job_id, job["buyer_id"], "settled", job["request"], job["state"])
        via = "timeout, model-only"
    store.event(job_id, "job.settled", {"via": via, "timeout_s": HUMAN_TIMEOUT_S})
    return True


def verdict(job_id: str) -> Verdict:
    if settle_on_timeout(job_id):
        pass
    job = store.get_job(job_id)
    if not job:
        raise KeyError(job_id)
    st = job["state"]
    by_claim = _answers_by_claim(job_id)
    cvs = [_claim_verdict(c, by_claim.get(c["idx"], [])) for c in st.get("claims", [])]
    lens_names = skus.lenses_for(job["request"].get("sku", "custom"), len(cvs))
    for cv, c, ln in zip(cvs, st.get("claims", []), lens_names):
        cv.lens = ln
        j = (st.get("replay") or {}).get("journeys", {}).get(str(c["idx"]))
        if j:
            cv.objective = {"source": "replay_qa", "journey_id": j["journey_id"], "result": j.get("result"), "bugs": j.get("bugs", [])}
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
    if st.get("timed_out"):
        summary = "Human panel did not answer in time; model-only verdict. " + summary
    if st.get("replay"):
        before = st["replay"].get("polled_at")
        st["replay"] = replay_client.refresh(job_id, st["replay"])
        if st["replay"].get("polled_at") != before:
            store.put_job(job_id, job["buyer_id"], job["status"], job["request"], st)
        summary += " " + replay_client.summary_line(st["replay"])
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
