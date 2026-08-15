"""report.json + agent.md + PDF: one data model (build), three renderings (to_agent_md, to_html,
to_pdf). Business findings come from state.claims (the Full Reality Check rubric, judge.py
verdict()); hackathon findings come from state.hackathon (docs/specs/output-first.md #20 wiring,
built by a parallel lane) when present, else the report says the rubric was not run.

Gap mapping (docs/specs/agent-report.md "Gaps" table): every lens in the Full Reality Check rubric
maps to one of payer / take_money / stranger_proof / loop. `loop` never carries findings; it is the
compounding section. Business stamp: ready_to_charge (payer + take_money have no fail) /
one_gap_away (exactly one gap has a fail) / not_yet.
"""
from __future__ import annotations

import html
from typing import Any

from reality_check import judge, skus, store

# --- gap mapping (docs/specs/agent-report.md gaps table) -------------------------------------

_LENS_GAP: dict[str, str] = {
    "clarity": "payer", "demand": "payer", "viability": "payer", "economics": "payer",
    "competition": "payer", "projections": "payer", "autonomy": "payer",
    "seo": "take_money", "legal": "take_money", "security": "take_money", "stability": "take_money",
    "accessibility": "take_money", "agent_ready": "take_money", "ux": "take_money", "trust": "take_money",
}
_GAP_TITLE = {"payer": "payer", "take_money": "take_money", "stranger_proof": "stranger_proof", "loop": "loop"}
_GAP_QUESTION = {
    "payer": "Does someone pay, and for what?",
    "take_money": "Can a stranger find it, trust it, and buy?",
    "stranger_proof": "Do people outside the team say the same thing?",
    "loop": "Is there a fix -> re-run -> delta path?",
}


def _gap_for(lens: str) -> str:
    return _LENS_GAP.get(lens, "stranger_proof")


def _claim_status(side: str, p: float | None, evidence_state: str) -> str:
    if evidence_state == "none":
        return "unknown"
    if p is None:
        return "partial"
    if side == "yes" and p >= 0.6:
        return "pass"
    if side == "no" and p <= 0.4:
        return "fail"
    return "partial"


def _business_finding(cv) -> dict[str, Any]:
    p = cv.p_humans if cv.p_humans is not None else cv.p_internal
    status = _claim_status(cv.verdict, p, cv.evidence_state)
    probe_backed = cv.objective is not None and (cv.objective or {}).get("source") in ("probes", "replay_qa")
    owner = "agent" if probe_backed else "human"
    gap = _gap_for(cv.lens)

    if status == "unknown":
        fix = "no evidence yet: give a live URL"
    else:
        fix = f"Say or show it: {cv.claim}"

    if probe_backed:
        failing = (cv.objective or {}).get("failing") or []
        evidence_list = (cv.objective or {}).get("evidence") or []
        evidence = {"kind": "probe", "failing": failing, "observed": evidence_list}
        acceptance = {"probe": failing[0] if failing else None, "must": "absent"}
    else:
        evidence: dict[str, Any] = {"kind": "human" if cv.n_humans else "model", "p": p}
        if cv.n_humans:
            evidence["n"] = cv.n_humans
            evidence["minority"] = cv.minority_view
        else:
            evidence["votes"] = cv.n_humans
            evidence["minority"] = cv.minority_view
        acceptance = {"claim": cv.claim_id, "must": "p >= 0.7"}

    return {
        "id": cv.claim_id, "lens": cv.lens, "gap": gap, "status": status, "owner": owner,
        "claim": cv.claim, "evidence": evidence, "fix": fix, "acceptance": acceptance,
        "severity": "error" if status == "fail" else "warn" if status == "partial" else "info",
    }


def _business_stamp(findings: list[dict]) -> str:
    by_gap: dict[str, list[dict]] = {}
    for f in findings:
        by_gap.setdefault(f["gap"], []).append(f)
    gap_has_fail = {g: any(x["status"] == "fail" for x in fs) for g, fs in by_gap.items()}
    core = ("payer", "take_money")
    failing_core = [g for g in core if gap_has_fail.get(g)]
    if not failing_core:
        return "ready_to_charge"
    if len(failing_core) == 1:
        return "one_gap_away"
    return "not_yet"


# --- hackathon section (state.hackathon, built by a parallel lane) ---------------------------

def _hackathon_findings(hackathon: dict) -> list[dict]:
    out: list[dict] = []
    for item in hackathon.get("judging", []):
        out.append({
            "id": item.get("id", ""), "section": "judging", "status": item.get("status", "unknown"),
            "owner": "agent" if str(item.get("id", "")).startswith("tech/") else "human",
            "claim": item.get("title", ""), "evidence": {"kind": "model", "why": item.get("why", "")},
            "fix": item.get("fix", ""), "acceptance": {"claim": item.get("id", ""), "must": "status = pass"},
            "severity": "error" if item.get("status") == "fail" else "warn" if item.get("status") == "partial" else "info",
        })
    for item in hackathon.get("sponsors", {}).get("claimed_not_evidenced", []) + \
            hackathon.get("sponsors", {}).get("cheapest_to_add", []):
        out.append({
            "id": item.get("id", ""), "section": "sponsors",
            "status": item.get("status", "unknown"),
            "owner": "agent" if item in hackathon.get("sponsors", {}).get("cheapest_to_add", []) else "human",
            "claim": item.get("name", ""), "evidence": {"kind": "model", "hints_found": item.get("hints_found", [])},
            "fix": item.get("fix", ""), "acceptance": {"claim": item.get("id", ""), "must": "status = qualifies"},
            "severity": "warn",
        })
    for item in hackathon.get("messaging", []):
        out.append({
            "id": item.get("id", ""), "section": "messaging", "status": item.get("status", "unknown"),
            "owner": "agent", "claim": item.get("theme", ""),
            "evidence": {"kind": "model", "where": item.get("where", "")},
            "fix": item.get("rewrite", ""), "acceptance": {"claim": item.get("id", ""), "must": "status = pass"},
            "severity": "warn",
        })
    for item in hackathon.get("technical", []) or []:
        out.append({
            "id": item.get("id", ""), "section": "technical", "status": item.get("status", "unknown"),
            "owner": "agent", "claim": item.get("title", item.get("claim", "")),
            "evidence": {"kind": "model", "why": item.get("why", "")},
            "fix": item.get("fix", ""), "acceptance": {"claim": item.get("id", ""), "must": "status = pass"},
            "severity": "warn",
        })
    return out


# --- compounding -------------------------------------------------------------------------------

def _compounding(job_id: str) -> dict[str, Any]:
    jobs = store.list_jobs(limit=200)
    settled = [j for j in jobs if j["status"] == "settled" and
               (j["request"].get("sku") == "full_reality_check" or j["state"].get("hackathon"))]
    n_reviewed = len(settled)
    ranked = []
    for j in settled:
        claims = j["state"].get("claims", [])
        passed = sum(1 for c in claims if c.get("consensus", {}).get("side") == "yes")
        ranked.append((j["job_id"], passed))
    ranked.sort(key=lambda x: x[1], reverse=True)
    rank = next((i + 1 for i, (jid, _p) in enumerate(ranked) if jid == job_id), None)
    fail_counts: dict[str, int] = {}
    for j in settled:
        for c in j["state"].get("claims", []):
            if c.get("consensus", {}).get("side") == "no":
                fail_counts[c.get("claim_id", "")] = fail_counts.get(c.get("claim_id", ""), 0) + 1
    common = sorted(fail_counts, key=lambda k: fail_counts[k], reverse=True)[:5]
    return {"n_reviewed": n_reviewed, "rank": rank, "common_failures": common}


# --- humans block (Terac / local panel) ---------------------------------------------------------

def _humans_block(job: dict) -> dict[str, Any]:
    answers = store.human_answers(job["job_id"])
    respondents = sorted({a["respondent"] for a in answers if a.get("respondent")})
    n = len(respondents)
    pending = job["status"] == "awaiting_humans" or n == 0
    return {"n": n, "pending": pending, "source": (job["state"].get("panel") or {}).get("source")}


# --- build ---------------------------------------------------------------------------------------

def build(job_id: str) -> dict:
    job = store.get_job(job_id)
    if job is None:
        raise KeyError(job_id)
    v = judge.verdict(job_id)
    st = job["state"]

    business_findings = [_business_finding(cv) for cv in v.claims]
    business_stamp = _business_stamp(business_findings)

    hackathon = st.get("hackathon")
    hackathon_findings = _hackathon_findings(hackathon) if hackathon else []
    hackathon_stamp = (hackathon or {}).get("stamp", "not_yet") if hackathon else "not_run"
    top3 = (hackathon or {}).get("top3") if hackathon else None
    if not top3:
        top3 = [f["fix"] for f in business_findings if f["status"] in ("fail", "unknown")][:3] or \
               ["Re-run with a live URL for objective evidence."]

    findings = business_findings + hackathon_findings
    compounding = _compounding(job_id)
    sources = st.get("sources") or {"source_kinds": [], "sources": []}

    return {
        "job": job_id,
        "generated_at": store.now(),
        "project": job["request"].get("buyer_id", "anonymous"),
        "input": {"url": job["request"].get("url"), "sku": job["request"].get("sku")},
        "stamps": {"hackathon": hackathon_stamp, "business": business_stamp},
        "top3": top3,
        "findings": findings,
        "hackathon": hackathon,
        "sources": sources,
        "evidence": {
            "read": (sources.get("sources") or []),
            "judged_by": {"n_evaluators": v.n_evaluators, "personas": job["request"].get("personas")},
            "humans": _humans_block(job),
        },
        "compounding": compounding,
    }


# --- agent.md --------------------------------------------------------------------------------

def _finding_md(f: dict) -> str:
    ev = f.get("evidence", {})
    if "failing" in ev:
        observed = "; ".join(ev.get("observed") or []) or "no probe evidence"
    elif ev.get("kind") == "human":
        observed = f"humans n={ev.get('n')} p={ev.get('p')}; minority: {ev.get('minority', '')}"
    elif ev.get("kind") == "model":
        observed = f"models p={ev.get('p')}; why: {ev.get('why', ev.get('minority', ''))}"
    else:
        observed = str(ev)
    acc = f.get("acceptance", {})
    done_when = f"{acc.get('probe')} is absent on the next run." if "probe" in acc else \
        f"{acc.get('claim')} reaches p >= 0.7 on re-run." if acc else "re-run and check."
    return (f"### {f['id']} [{f['status']}]\n"
            f"Evidence: {observed}\n"
            f"Fix: {f['fix']}\n"
            f"Done when: {done_when}\n")


def to_agent_md(report: dict) -> str:
    stamps = report["stamps"]
    lines = [
        f"# Reality Check ({report['job']})",
        f"Hackathon: {stamps['hackathon'].upper()}   Business: {stamps['business'].upper()}",
        "do not invent facts; every item cites evidence",
        "",
    ]
    findings = report["findings"]
    agent_owned = [f for f in findings if f.get("owner") == "agent"]
    human_owned = [f for f in findings if f.get("owner") != "agent"]
    business_gaps = [f for f in findings if "gap" in f]
    repo_advice = [f for f in findings if f.get("section") == "technical"]

    lines.append("## Fix before 18:30 (agent-owned)")
    for f in agent_owned:
        lines.append(_finding_md(f))
    lines.append("## Needs a human decision")
    for f in human_owned:
        lines.append(_finding_md(f))
    lines.append("## Business gaps")
    for gap in ("payer", "take_money", "stranger_proof", "loop"):
        gap_findings = [f for f in business_gaps if f["gap"] == gap]
        if not gap_findings:
            continue
        lines.append(f"### {gap}")
        for f in gap_findings:
            lines.append(_finding_md(f))
    lines.append("## Repo advice")
    if repo_advice:
        for f in repo_advice:
            lines.append(_finding_md(f))
    else:
        lines.append("(no repo supplied, or no repo-scoped findings)")
    return "\n".join(lines)


# --- HTML / PDF --------------------------------------------------------------------------------

_PILL = {"pass": "p-good", "fail": "p-bad", "partial": "p-warn", "unknown": "p-na",
         "qualifies": "p-good", "claimed_not_evidenced": "p-warn", "not_used": "p-na",
         "contender": "p-good", "fixable_by_1830": "p-warn", "not_yet": "p-bad", "not_run": "p-na",
         "ready_to_charge": "p-good", "one_gap_away": "p-warn"}


def _pill(status: str) -> str:
    cls = _PILL.get(status, "p-na")
    return f'<span class="pill {cls}">{html.escape(status)}</span>'


def _sponsor_table(hackathon: dict | None) -> str:
    rows = []
    if hackathon:
        sp = hackathon.get("sponsors", {})
        for bucket, label in (("qualifies", "qualifies"), ("claimed_not_evidenced", "claimed, not evidenced"),
                               ("cheapest_to_add", "cheapest to add"), ("not_used", "not used")):
            for item in sp.get(bucket, []):
                rows.append(f"<tr><td><b>{html.escape(item.get('name', item.get('id', '')))}</b></td>"
                            f"<td>{html.escape(str(item.get('required', '')))}</td>"
                            f"<td>{_pill(item.get('status', bucket))}</td>"
                            f"<td>{html.escape(item.get('why', ''))}</td></tr>")
    if not rows:
        rows = ["<tr><td colspan=4>hackathon rubric not run</td></tr>"]
    return ('<h2>Sponsor tracks</h2><div class="tw"><table><tr><th>Track</th><th>Prize</th>'
            f'<th>Status</th><th>Evidence / what is missing</th></tr>{"".join(rows)}</table></div>')


def _humans_card(report: dict) -> str:
    h = report["evidence"]["humans"]
    if h.get("pending") or not h.get("n"):
        return ('<div class="card"><div class="k">Humans (Terac)</div>'
                '<div>humans pending<br><span class="note">Report is valid without them; re-check when they land.</span></div></div>')
    return (f'<div class="card"><div class="k">{h["n"]} strangers from Terac\'s network read it</div>'
            f'<div>source: {html.escape(str(h.get("source") or ""))}</div></div>')


def _judging_table(hackathon: dict | None) -> str:
    if not hackathon or not hackathon.get("judging"):
        return "<p class='note'>hackathon rubric not run.</p>"
    rows = []
    for it in hackathon["judging"]:
        rows.append(f"<tr><td><span class='id'>{html.escape(it.get('id',''))}</span></td>"
                    f"<td>{it.get('weight','')}</td><td>{_pill(it.get('status','unknown'))}</td>"
                    f"<td>{html.escape(it.get('why',''))}</td><td>{html.escape(it.get('fix',''))}</td></tr>")
    return ('<div class="tw"><table><tr><th>Judging item</th><th>Weight</th><th>Result</th><th>Why</th><th>Fix</th></tr>'
            f'{"".join(rows)}</table></div>')


def _messaging_list(hackathon: dict | None) -> str:
    if not hackathon or not hackathon.get("messaging"):
        return "<p class='note'>no messaging findings.</p>"
    items = "".join(f"<li><span class='id'>{html.escape(m.get('id',''))}</span> "
                     f"{html.escape(m.get('where',''))}: {html.escape(m.get('rewrite',''))}</li>"
                     for m in hackathon["messaging"])
    return f"<ul>{items}</ul>"


def _business_gap_cards(findings: list[dict]) -> str:
    cards = []
    for gap in ("payer", "take_money", "stranger_proof", "loop"):
        gap_findings = [f for f in findings if f.get("gap") == gap]
        fails = [f for f in gap_findings if f["status"] == "fail"]
        color = "bad" if fails else "warn" if any(f["status"] == "partial" for f in gap_findings) else "good"
        body = "; ".join(f"{f['id']}: {f['status']}" for f in gap_findings) or "no findings"
        cards.append(f'<div class="card"><div class="k">{gap} <span class="pill p-{"bad" if color=="bad" else "warn" if color=="warn" else "good"}">{color}</span></div><div>{html.escape(body)}</div></div>')
    return f'<div class="grid2">{"".join(cards)}</div>'


def _repo_advice(findings: list[dict]) -> str:
    tech = [f for f in findings if f.get("section") == "technical"]
    if not tech:
        return ""
    items = "".join(f"<li><span class='id'>{html.escape(f['id'])}</span> {html.escape(f['fix'])}</li>" for f in tech)
    return (f'<section class="page" data-page="PDF page 4">'
            f'<h2>From vibe-coded to an MVP</h2><p class="note">Repo supplied; agent-fixable first, same items are in agent.md.</p>'
            f'<ul>{items}</ul></section>')


def to_html(report: dict) -> str:
    stamps = report["stamps"]
    comp = report["compounding"]
    top3 = "".join(f"<li>{html.escape(t)}</li>" for t in report["top3"])
    page1 = (
        '<section class="page" data-page="PDF page 1">'
        f'<div class="eyebrow">Reality Check, job <span class="id">{html.escape(report["job"])}</span></div>'
        f'<h1>{html.escape(str(report.get("project", "")))}</h1>'
        f'<div class="stamps"><span class="stamp warn">Hackathon: {html.escape(stamps["hackathon"])}</span>'
        f'<span class="stamp bad">Business: {html.escape(stamps["business"])}</span></div>'
        f'<div class="grid2"><div class="card"><div class="k">Do these before you submit</div><ol>{top3}</ol></div>'
        f'{_humans_card(report)}</div>'
        f'{_sponsor_table(report.get("hackathon"))}'
        f'<div class="foot">Stamp rules: hackathon = contender/fixable_by_1830/not_yet by judging weight-3 items; '
        f'business = ready_to_charge/one_gap_away/not_yet by the four gaps. '
        f'{comp["n_reviewed"]} projects reviewed; this one ranks {comp.get("rank")}.</div>'
        '</section>'
    )
    page2 = ('<section class="page" data-page="PDF page 2"><h2>How to win this hackathon</h2>'
             f'{_judging_table(report.get("hackathon"))}<h3>Messaging</h3>{_messaging_list(report.get("hackathon"))}</section>')
    page3 = ('<section class="page" data-page="PDF page 3"><h2>Is it a business</h2>'
             f'{_business_gap_cards(report["findings"])}</section>')
    page4 = _repo_advice(report["findings"])
    evidence = report.get("sources", {})
    read = ", ".join(str(s.get("kind", "")) for s in evidence.get("sources", [])) or "no sources read"
    last = (f'<section class="page" data-page="evidence"><h2>Evidence</h2>'
            f'<p>Read: {html.escape(read)}. Humans: {report["evidence"]["humans"]}.</p>'
            f'<div class="foot">Re-run: POST /intake/{html.escape(report["job"])}/redeploy or resubmit the same links.</div></section>')
    agent_md = html.escape(to_agent_md(report))
    return (f'<!doctype html><title>Reality Check {html.escape(report["job"])}</title>'
            '<style>body{font:15px/1.5 -apple-system,system-ui,sans-serif;max-width:860px;margin:2rem auto;padding:0 1rem}'
            '.page{border:1px solid #ddd;padding:24px;margin-bottom:24px;page-break-after:always}'
            '.stamp{border:2px solid;padding:6px 10px;font-weight:700;margin-right:8px}'
            '.pill{padding:1px 8px;font-size:12px;font-weight:700}.p-good{background:#1f7a3f;color:#fff}'
            '.p-bad{background:#b3261e;color:#fff}.p-warn{background:#b7791f;color:#fff}.p-na{background:#ddd}'
            'table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;padding:6px;text-align:left}'
            '.grid2{display:flex;gap:16px}.card{background:#f2f0ea;padding:12px;flex:1}'
            '.id{font-family:monospace}pre{white-space:pre-wrap;background:#eee;padding:12px}'
            '@page{size:A4;margin:2cm}</style>'
            f'{page1}{page2}{page3}{page4}{last}'
            f'<section><h2>agent.md</h2><pre>{agent_md}</pre></section>')


def to_pdf(report: dict) -> bytes | None:
    try:
        from xhtml2pdf import pisa
    except Exception:
        return None
    import io
    out = io.BytesIO()
    try:
        result = pisa.CreatePDF(io.StringIO(to_html(report)), dest=out)
    except Exception:
        return None
    if result.err:
        return None
    data = out.getvalue()
    return data if data[:4] == b"%PDF" else None
