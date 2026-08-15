"""FastAPI surface.

POST /judge                 buyer (agent or paid human) submits a judgment request
POST /intake                verified_autonomous intake (claims + invariants, builder-blind); Replay QA project + per-flow-claim journeys
POST /intake/{id}/redeploy  team shipped a fix: Replay re-tests, verdict shows open bugs before -> after
POST /order, GET /order/{id} pay-first flow (stripe_webhook.py): pending job -> Payment Link -> poller/webhook starts it
GET  /judge/{job_id}        verdict so far
GET  /rate/{job_id}         human rating page (Terac activity task_url / Linq link / room QR)
POST /rate/{job_id}         human answer
POST /before_after/lock/{b} lock the "before" verdict hash; GET /before_after/{b}/{a} compare
GET  /ledger /events /jobs /learning   receipts, decision log, verdicts, arm gains + evaluator reputation
GET  /                      dashboard

Paid status is a receipt (Stripe session in the ledger), never a claim: protocol.admit() reads it;
X-RC-Paid is honoured only when RC_DEV=1.
"""
from __future__ import annotations

import html
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from reality_check import before_after, intake, judge, skus, store, stripe_poll, stripe_webhook, terac_client
from reality_check.core.models import JudgeRequest, Verdict
from reality_check.policy import envelope, learning, protocol


@asynccontextmanager
async def _lifespan(app: FastAPI):
    store.event(None, "envelope.bootstrap", {"status": envelope.bootstrap()})
    stripe_poll.start_background()
    yield


app = FastAPI(title="Reality Check", version="0.0.1", lifespan=_lifespan)
store.init()
# Storefront (Lovable) is a separate origin reading public JSON; no credentials cross.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["*"], allow_credentials=False)
app.include_router(stripe_webhook.router)
terac_client.register()

TERAC_CALLBACK = "https://terac.com/api/external/callback"


async def _admit(request: Request) -> tuple[dict, protocol.Admission]:
    body = await request.json()
    adm = protocol.admit(body, headers=dict(request.headers))
    if not adm.admitted:
        raise HTTPException(409, adm.reason)
    return body, adm


@app.post("/judge", response_model=Verdict)
async def post_judge(request: Request) -> Verdict:
    body, adm = await _admit(request)
    try:
        req = JudgeRequest(**body)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    job_id = uuid.uuid4().hex[:12]
    protocol.record(job_id, adm)
    return judge.start(req, paid_usd=adm.paid_usd, job_id=job_id)


@app.post("/intake", response_model=Verdict)
async def post_intake(request: Request) -> Verdict:
    body, adm = await _admit(request)
    try:
        req = intake.IntakeRequest(**body)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    req.paid_usd = adm.paid_usd
    return intake.submit(req)


@app.post("/intake/{job_id}/redeploy")
def post_redeploy(job_id: str, req: intake.RedeployRequest) -> dict:
    try:
        return intake.redeploy(job_id, req)
    except KeyError:
        raise HTTPException(404, "no such job")


@app.post("/before_after/lock/{job_id}")
def before_after_lock(job_id: str) -> dict:
    if not store.get_job(job_id):
        raise HTTPException(404, "no such job")
    return {"job_id": job_id, "before_hash": before_after.lock(job_id)}


@app.get("/before_after/{before_id}/{after_id}")
def before_after_compare(before_id: str, after_id: str) -> dict:
    return before_after.compare(before_id, after_id)


@app.get("/learning")
def learning_report() -> dict:
    return learning.report()


@app.get("/skus")
def list_skus() -> dict:
    return skus.SKUS


@app.get("/judge/{job_id}", response_model=Verdict)
def get_judge(job_id: str) -> Verdict:
    try:
        return judge.verdict(job_id)
    except KeyError:
        raise HTTPException(404, "no such job")


RATER_COOKIE = "rc_r"


@app.get("/rate/{job_id}", response_class=HTMLResponse)
def rate_page(job_id: str, request: Request, response: Response, src: str = "local", r: str | None = None, teracSubmissionId: str | None = None) -> str:
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    # venue NAT: every phone shares one IP, so anonymous respondents get a uuid, never the client
    # IP. The uuid sticks in a cookie so the same phone keeps one identity across jobs: that is
    # what makes "fresh eyes" on a before/after enforceable for in-room raters too.
    sticky = request.cookies.get(RATER_COOKIE)
    respondent = teracSubmissionId or r or sticky or uuid.uuid4().hex[:12]
    if not teracSubmissionId and not r and not sticky:
        response.set_cookie(RATER_COOKIE, respondent, max_age=86400, samesite="lax")
    if teracSubmissionId:
        src = "terac"
    hq = html.escape(job["state"].get("human_question") or "")
    body = html.escape(job["request"]["input"][:4000])
    claims = job["request"]["claims"]
    qs = "".join(
        f'<fieldset><legend>{i+1}. {html.escape(c)}</legend>'
        f'<label><input type=radio name="c{i}" value=yes required> Yes</label> &nbsp; '
        f'<label><input type=radio name="c{i}" value=no> No</label></fieldset>'
        for i, c in enumerate(claims))
    return f"""<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">
<title>Reality Check</title>
<style>body{{font:16px/1.5 -apple-system,system-ui,sans-serif;max-width:640px;margin:2rem auto;padding:0 1rem;color:#111}}
pre{{white-space:pre-wrap;background:#f4f4f4;padding:1rem;border-radius:8px;max-height:40vh;overflow:auto}}
fieldset{{border:1px solid #ddd;border-radius:8px;margin:.8rem 0;padding:.6rem 1rem}}legend{{font-weight:600}}
button{{font:inherit;padding:.8rem 1.4rem;border-radius:8px;border:1px solid #111;background:#fff;cursor:pointer}}
textarea{{width:100%;min-height:5rem;font:inherit;padding:.6rem}}</style>
<h1>Honest answers, please</h1>
<p>Read this:</p><pre>{body}</pre>
<form method=post action="/rate/{job_id}">
<input type=hidden name=src value="{html.escape(src)}"><input type=hidden name=respondent value="{html.escape(respondent)}">
<input type=hidden name=n_claims value="{len(claims)}">
{qs}
<p>{hq or "In one sentence, what is this about, or what would change your mind?"}</p>
<textarea name=free_text></textarea>
<p><button type=submit>Submit</button></p></form>"""


@app.post("/rate/{job_id}")
async def rate_submit(job_id: str, request: Request):
    if not store.get_job(job_id):
        raise HTTPException(404, "no such job")
    form = await request.form()
    src = str(form.get("src", "local"))
    respondent = str(form.get("respondent", "")) or uuid.uuid4().hex[:12]
    job = store.get_job(job_id)
    prev = (job["request"].get("before_job_id") if job else None)
    if prev and any(a["respondent"] == respondent for a in store.human_answers(prev)):
        store.event(job_id, "human.rejected", {"reason": "judged the previous version", "before_job_id": prev})
        return HTMLResponse("<meta name=viewport content='width=device-width'><p style='font:18px system-ui;margin:3rem'>You already judged the previous version; this round needs fresh eyes. Thank you.</p>")
    free_text = str(form.get("free_text", ""))
    n = int(form.get("n_claims", 1))
    accepted = 0
    for i in range(n):
        v = form.get(f"c{i}")
        yes = True if v == "yes" else False if v == "no" else None
        accepted += int(store.add_human_answer(job_id, src, respondent, yes, free_text if i == 0 else "", claim_idx=i))
    if not accepted:
        store.event(job_id, "human.duplicate", {"src": src, "respondent": respondent[:16]})
        return HTMLResponse("<meta name=viewport content='width=device-width'><p style='font:18px system-ui;margin:3rem'>Already counted. Thank you.</p>")
    store.event(job_id, "human.answered", {"src": src, "n_claims": n})
    judge.on_human_answer(job_id)
    if src == "terac" and form.get("respondent"):
        return RedirectResponse(f"{TERAC_CALLBACK}?teracSubmissionId={respondent}&result=completed", status_code=303)
    return HTMLResponse("<meta name=viewport content='width=device-width'><p style='font:18px system-ui;margin:3rem'>Thanks. That's it.</p>")


@app.get("/verdict/{job_id}", response_class=HTMLResponse)
def verdict_page(job_id: str) -> str:
    """Buyer-facing verdict, one block per lens: verdict, evidence source, n, cost. Plain text on purpose."""
    try:
        v = judge.verdict(job_id)
    except KeyError:
        raise HTTPException(404, "no such job")
    by_lens: dict[str, list] = {}
    for cv in v.claims:
        by_lens.setdefault(cv.lens, []).append(cv)
    order = [l for l in skus.LENS_ORDER if l in by_lens] + [l for l in by_lens if l not in skus.LENS_ORDER]
    blocks = []
    for lens in order:
        rows = "".join(
            f"<li><b>{html.escape(cv.verdict)}</b> {html.escape(cv.claim)} "
            f"<small>models p={cv.p_internal:.2f}" + (f", humans {cv.n_humans} p={cv.p_humans:.2f}" if cv.p_humans is not None else "") +
            (f", replay {html.escape(str(cv.objective.get('result')))}" if cv.objective else "") + "</small>"
            + (f"<br><i>minority: {html.escape(cv.minority_view)}</i>" if cv.minority_view else "") + "</li>"
            for cv in by_lens[lens])
        passed = sum(1 for cv in by_lens[lens] if cv.verdict == "yes")
        blocks.append(f"<h2>{lens}: {passed}/{len(by_lens[lens])} hold</h2><ul>{rows}</ul>")
    voi = v.voi
    econ = (f"<h2>economics</h2><p>revenue ${v.revenue_usd:.2f}, evidence cost ${v.evidence_cost_usd:.2f}, margin ${v.margin_usd:.2f}.<br>"
            f"router: {html.escape(voi.reason) if voi else 'n/a'}" + (f" (net value ${voi.net_value_usd:.2f})" if voi else "") + "</p>")
    return f"""<!doctype html><meta name=viewport content="width=device-width,initial-scale=1"><title>Reality Check verdict</title>
<style>body{{font:16px/1.5 -apple-system,system-ui,sans-serif;max-width:720px;margin:2rem auto;padding:0 1rem;color:#111}}h2{{margin-top:1.6rem;font-size:1.1rem}}li{{margin:.5rem 0}}small,i{{color:#555}}</style>
<h1>Verdict: {html.escape(v.verdict)} <small>(p={v.p:.2f}, {v.status})</small></h1>
<p>{html.escape(v.summary)}</p>{''.join(blocks)}{econ}
<p><small>job {v.job_id}. Human answers: {v.n_humans}. Evaluators: {v.n_evaluators}.</small></p>"""


@app.get("/summary")
def summary() -> dict:
    """One call for the storefront dashboard: money, counts, learning lines, recent jobs (compact)."""
    t = store.ledger_totals()
    vs = [judge.verdict(j["job_id"]) for j in store.list_jobs(limit=30)]
    by_status: dict[str, int] = {}
    for v in vs:
        by_status[v.status] = by_status.get(v.status, 0) + 1
    rep = learning.report()
    return {
        "money": t,
        "counts": {"jobs": len(vs), "by_status": by_status, "humans": sum(v.n_humans for v in vs),
                   "voi_bought": sum(1 for v in vs if v.voi and v.voi.buy), "voi_declined": sum(1 for v in vs if v.voi and not v.voi.buy)},
        "learning": {"swarm_check": rep.get("swarm_check"), "arms": rep.get("arms")},
        "skus": {k: {"price_usd": v["price_usd"], "evidence_standard": v.get("evidence_standard", "voi_routed"), "claims": v["claims"]}
                 for k, v in skus.SKUS.items() if k != "custom"},
        "pay_links": {k: stripe_webhook.pay_link(k) for k in ("reality_check", "full_reality_check")},
        "recent": [{"job_id": v.job_id, "status": v.status, "verdict": v.verdict, "p": v.p, "n_humans": v.n_humans,
                    "sku": (store.get_job(v.job_id) or {}).get("request", {}).get("sku"),
                    "voi": {"buy": v.voi.buy, "arm": v.voi.arm, "reason": v.voi.reason} if v.voi else None,
                    "revenue_usd": v.revenue_usd, "evidence_cost_usd": v.evidence_cost_usd, "summary": v.summary} for v in vs],
    }


@app.get("/ledger")
def ledger() -> dict:
    return store.ledger_totals()


@app.get("/events")
def events(limit: int = Query(200, le=1000)) -> list[dict]:
    return store.events(limit)


@app.get("/jobs")
def jobs() -> list[dict]:
    return [judge.verdict(j["job_id"]).model_dump() for j in store.list_jobs()]


def _learning_lines() -> str:
    rep = learning.report()
    if rep.get("error"):
        return html.escape(f"learning unavailable: {rep['error']}")
    sc = rep["swarm_check"]
    f3 = lambda x: "n/a" if x is None else f"{x:.3f}"  # noqa: E731
    if not sc.get("n_jobs"):
        l1 = "Swarm check: unmeasured until 3 jobs settle against humans."
    else:
        l1 = (f"Swarm check ({sc['n_jobs']} settled jobs): {sc['verdict']}. Ensemble brier {f3(sc.get('ensemble_brier'))} "
              f"vs lone agent median {f3(sc.get('median_single_brier'))} / best {f3(sc.get('best_single_brier'))}; "
              f"ensemble cost ${sc.get('ensemble_cost_usd') or 0:.3f} vs one agent ${sc.get('single_cost_usd') or 0:.3f}.")
    live = [a for a in rep["arms"].values() if a.get("n_settled")]
    if not live:
        l2 = "Where humans beat the models: no settled human panels yet; VOI is running on priors."
    else:
        l2 = "Where humans beat the models: " + " · ".join(
            f"{a['arm']}: gain {(a.get('measured_gain') or 0):.0%} ({'measured' if a.get('live') else 'prior until n>=10'}, "
            f"n={a['n_settled']}, overturned {a.get('overturned_jobs', 0)})" for a in live)
    return html.escape(l1) + "<br>" + html.escape(l2)


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    t = store.ledger_totals()
    rows = "".join(
        f"<tr><td>{v.job_id}</td><td>{v.status}</td><td>{v.verdict} ({v.p:.2f})</td><td>{v.n_evaluators}/{v.n_humans}</td>"
        f"<td>{'buy '+v.voi.arm if v.voi and v.voi.buy else 'no buy'}</td><td>${v.revenue_usd:.2f}</td><td>${v.evidence_cost_usd:.2f}</td>"
        f"<td>{html.escape(v.summary)}</td></tr>"
        for v in (judge.verdict(j["job_id"]) for j in store.list_jobs()))
    ev = "".join(f"<li><code>{e['at']}</code> {e['kind']} <small>{html.escape(str(e['payload']))[:200]}</small></li>" for e in store.events(40))
    return f"""<!doctype html><meta http-equiv=refresh content=5><title>Reality Check</title>
<style>body{{font:14px/1.4 -apple-system,system-ui,sans-serif;margin:2rem;color:#111}}table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #ddd;padding:.4rem;text-align:left;vertical-align:top}}.k{{font-size:2rem;margin-right:2rem}}</style>
<h1>Reality Check</h1>
<p><span class=k>revenue ${t['revenue_usd']:.2f}</span><span class=k>evidence cost ${t['cost_usd']:.2f}</span><span class=k>margin ${t['margin_usd']:.2f}</span></p>
<p>{_learning_lines()}</p>
<table><tr><th>job</th><th>status</th><th>verdict</th><th>models/humans</th><th>VOI</th><th>rev</th><th>cost</th><th>summary</th></tr>{rows}</table>
<h2>Decision log</h2><ul>{ev}</ul>"""
