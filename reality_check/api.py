"""FastAPI surface.

POST /judge                 buyer (agent or paid human) submits a judgment request
GET  /judge/{job_id}        verdict so far
GET  /rate/{job_id}         human rating page (Terac activity task_url / Linq link / room QR)
POST /rate/{job_id}         human answer
GET  /ledger                revenue, evidence cost, margin
GET  /events                decision log (what the company did and why)
GET  /                      dashboard (reads the three above)

Payment gating (Stripe webhook -> start job) is wired by stripe_webhook.py (money-swarm session);
until then /judge accepts an `X-RC-Paid` header for local testing only.
"""
from __future__ import annotations

import html
import os

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from reality_check import intake, judge, skus, store
from reality_check.core.models import JudgeRequest, Verdict

app = FastAPI(title="Reality Check", version="0.0.1")
store.init()

TERAC_CALLBACK = "https://terac.com/api/external/callback"


@app.post("/judge", response_model=Verdict)
def post_judge(req: JudgeRequest, x_rc_paid: str | None = Header(default=None)) -> Verdict:
    paid = float(x_rc_paid) if x_rc_paid else 0.0
    return judge.start(req, paid_usd=paid)


@app.post("/intake", response_model=Verdict)
def post_intake(req: intake.IntakeRequest, x_rc_paid: str | None = Header(default=None)) -> Verdict:
    if x_rc_paid:
        req.paid_usd = float(x_rc_paid)
    return intake.submit(req)


@app.get("/skus")
def list_skus() -> dict:
    return skus.SKUS


@app.get("/judge/{job_id}", response_model=Verdict)
def get_judge(job_id: str) -> Verdict:
    try:
        return judge.verdict(job_id)
    except KeyError:
        raise HTTPException(404, "no such job")


@app.get("/rate/{job_id}", response_class=HTMLResponse)
def rate_page(job_id: str, src: str = "local", r: str | None = None, teracSubmissionId: str | None = None) -> str:
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    respondent = teracSubmissionId or r or ""
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
    respondent = str(form.get("respondent", "")) or (request.client.host if request.client else "anon")
    free_text = str(form.get("free_text", ""))
    n = int(form.get("n_claims", 1))
    for i in range(n):
        v = form.get(f"c{i}")
        yes = True if v == "yes" else False if v == "no" else None
        store.add_human_answer(job_id, src, respondent, yes, free_text if i == 0 else "", claim_idx=i)
    store.event(job_id, "human.answered", {"src": src, "n_claims": n})
    judge.on_human_answer(job_id)
    if src == "terac" and form.get("respondent"):
        return RedirectResponse(f"{TERAC_CALLBACK}?teracSubmissionId={respondent}&result=completed", status_code=303)
    return HTMLResponse("<meta name=viewport content='width=device-width'><p style='font:18px system-ui;margin:3rem'>Thanks. That's it.</p>")


@app.get("/ledger")
def ledger() -> dict:
    return store.ledger_totals()


@app.get("/events")
def events(limit: int = Query(200, le=1000)) -> list[dict]:
    return store.events(limit)


@app.get("/jobs")
def jobs() -> list[dict]:
    return [judge.verdict(j["job_id"]).model_dump() for j in store.list_jobs()]


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
<table><tr><th>job</th><th>status</th><th>verdict</th><th>models/humans</th><th>VOI</th><th>rev</th><th>cost</th><th>summary</th></tr>{rows}</table>
<h2>Decision log</h2><ul>{ev}</ul>"""
