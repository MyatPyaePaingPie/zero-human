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

import pathlib

import html
import re
from typing import Any

from reality_check import hackathon, judge, skus, store

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
        fix = f"Make it true and put it where a stranger sees it in ten seconds (hero, first slide, README top): {cv.claim}"

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


# --- autonomy (state.hackathon.autonomy, 7 failure modes) ------------------------------------

def _autonomy_rubric_by_id() -> dict[str, dict]:
    try:
        rubric = hackathon.load_rubric()
    except Exception:
        return {}
    return {item.get("id"): item for item in (rubric.get("autonomy") or {}).get("items", [])}


def _autonomy_section(hackathon_state: dict | None) -> dict | None:
    """report.json top-level "autonomy": {"stamp","k_hold","items":[...]}. None when the job
    predates the autonomy rubric (tolerate absence)."""
    if not hackathon_state or not hackathon_state.get("autonomy"):
        return None
    rubric_by_id = _autonomy_rubric_by_id()
    items = []
    k_hold = 0
    for a in hackathon_state["autonomy"]:
        rubric_item = rubric_by_id.get(a.get("id"), {})
        status = a.get("status", "unknown")
        if status == "pass":
            k_hold += 1
        items.append({
            "id": a.get("id"), "title": a.get("title"), "failure": a.get("failure"),
            "status": status, "score": a.get("score"), "why": a.get("why"), "fix": a.get("fix"),
            "plain": rubric_item.get("plain", ""), "look_for": rubric_item.get("look_for", ""),
            "evidence_public": rubric_item.get("evidence_public", []),
        })
    return {"stamp": hackathon_state.get("autonomy_stamp", "not_run"), "k_hold": k_hold,
            "n": len(items), "note": hackathon_state.get("autonomy_note", ""), "items": items}


def _autonomy_findings(autonomy: dict | None) -> list[dict]:
    if not autonomy:
        return []
    out = []
    for it in autonomy["items"]:
        out.append({
            "id": it["id"], "section": "autonomy", "status": it["status"],
            "owner": "human", "claim": it["title"],
            "evidence": {"kind": "model", "why": it.get("why", ""), "plain": it.get("plain", ""),
                        "evidence_public": it.get("evidence_public", [])},
            "fix": it.get("fix", ""), "acceptance": {"claim": it["id"], "must": "status = pass"},
            "severity": "error" if it["status"] == "fail" else "warn" if it["status"] == "partial" else "info",
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

    autonomy = _autonomy_section(hackathon)
    autonomy_findings = _autonomy_findings(autonomy)

    findings = business_findings + hackathon_findings + autonomy_findings
    compounding = _compounding(job_id)
    sources = st.get("sources") or {"source_kinds": [], "sources": []}

    return {
        "job": job_id,
        "generated_at": store.now(),
        "project": job["request"].get("buyer_id", "anonymous"),
        "input": {"url": job["request"].get("url"), "sku": job["request"].get("sku")},
        "stamps": {"hackathon": hackathon_stamp, "business": business_stamp,
                   "autonomous": autonomy["stamp"] if autonomy else "not_run"},
        "top3": top3,
        "findings": findings,
        "hackathon": hackathon,
        "autonomy": autonomy,
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
    if f.get("section") == "autonomy":
        observed = ev.get("plain", "") or ev.get("why", "")
        pub = ev.get("evidence_public") or []
        if pub and f["status"] in ("fail", "partial"):
            observed += f"  Public: {pub[0].get('what', '')} ({pub[0].get('url', '')})"
    elif "failing" in ev:
        observed = "; ".join(ev.get("observed") or []) or "no probe evidence"
    elif ev.get("kind") == "human":
        observed = f"humans n={ev.get('n')} p={ev.get('p')}; minority: {ev.get('minority', '')}"
    elif ev.get("kind") == "model":
        observed = f"models p={ev.get('p')}; why: {ev.get('why', ev.get('minority', ''))}"
    else:
        observed = str(ev)
    acc = f.get("acceptance", {})
    if acc.get("probe"):
        done_when = f"{acc.get('probe')} is absent on the next run."
    elif "probe" in acc:
        done_when = "keeps passing on the next run."
    elif acc.get("must") == "status = pass":
        done_when = f"{acc.get('claim')} reaches status = pass on re-run."
    else:
        done_when = f"{acc.get('claim')} reaches p >= 0.7 on re-run." if acc else "re-run and check."
    # a person talking to a team: the action first, the evidence, the finish line; the id last and small
    status_word = {"pass": "holds", "fail": "missing", "partial": "half there", "unknown": "no evidence yet"}.get(f["status"], f["status"])
    return (f"### {f['fix']}\n"
            f"What we saw ({status_word}): {observed}\n"
            f"Done when: {done_when}\n"
            f"<sub>{f['id']}</sub>\n")


def to_agent_md(report: dict) -> str:
    stamps = report["stamps"]
    lines = [
        f"# Reality Check ({report['job']})",
        f"Hackathon: {_stamp_word('hackathon', stamps['hackathon'])}   "
        f"Autonomous: {_autonomy_word(report.get('autonomy'))}   "
        f"Business: {_stamp_word('business', stamps['business'])}",
        "do not invent facts; every item cites evidence",
        "",
    ]
    findings = [f for f in report["findings"] if f.get("section") != "autonomy"]
    autonomy_findings = [f for f in report["findings"] if f.get("section") == "autonomy"]
    agent_owned = [f for f in findings if f.get("owner") == "agent"]
    human_owned = [f for f in findings if f.get("owner") != "agent"]
    business_gaps = [f for f in findings if "gap" in f]
    repo_advice = [f for f in findings if f.get("section") == "technical"]

    def _open(fs: list[dict]) -> list[dict]:
        return [f for f in fs if f.get("status") != "pass"]

    def _passing_line(fs: list[dict]) -> str:
        ok = [f["id"] for f in fs if f.get("status") == "pass"]
        return f"Already passing ({len(ok)}): " + ", ".join(ok) if ok else ""

    lines.append("## Fix before 18:30 (agent-owned)")
    for f in _open(agent_owned):
        lines.append(_finding_md(f))
    if _passing_line(agent_owned):
        lines.append(_passing_line(agent_owned) + "\n")
    lines.append("## Needs a human decision")
    for f in _open(human_owned):
        lines.append(_finding_md(f))
    if _passing_line(human_owned):
        lines.append(_passing_line(human_owned) + "\n")
    if autonomy_findings:
        autonomy = report.get("autonomy") or {}
        lines.append(f"## Can it run autonomously ({autonomy.get('k_hold', 0)} of {autonomy.get('n', len(autonomy_findings))} hold, {str(autonomy.get('stamp', 'not_run')).upper()})")
        for f in autonomy_findings:
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
    rubric_by_id = _sponsor_rubric_by_id()

    def _rubric_name(item: dict) -> str:
        return rubric_by_id.get(item.get("id"), {}).get("name") or item.get("name") or item.get("id", "")

    def _row(item: dict) -> str:
        rname = _rubric_name(item)
        track, prize = _sponsor_track_prize(rname)
        if not prize:
            prize = "required rule" if item.get("required") else ""
        return (f"<tr><td><b>{html.escape(track)}</b></td><td>{html.escape(prize)}</td>"
                f"<td>{_pill(item.get('status', 'unknown'))}</td>"
                f"<td>{html.escape(item.get('why', ''))}</td></tr>")

    rows: list[str] = []
    if hackathon:
        sp = hackathon.get("sponsors", {})
        entries = [it for bucket in ("qualifies", "claimed_not_evidenced", "cheapest_to_add")
                   for it in sp.get(bucket, [])]
        terac = next((it for it in entries if it.get("id") == "sponsor/terac"), None)
        stripe = next((it for it in entries if it.get("id") == "sponsor/stripe"), None)
        rest = [it for it in entries if it.get("id") not in ("sponsor/terac", "sponsor/stripe")]
        rest.sort(key=lambda it: (not it.get("required"), -_prize_amount(_sponsor_track_prize(_rubric_name(it))[1])))
        for it in [x for x in (terac, stripe) if x] + rest:
            rows.append(_row(it))
        not_used = sp.get("not_used", [])
        if not_used:
            names = ", ".join(_short_name(_rubric_name(it)) for it in not_used)
            rows.append(f"<tr><td colspan='4'>Not used: {html.escape(names)}</td></tr>")
    if not rows:
        rows = ["<tr><td colspan=4>hackathon rubric not run</td></tr>"]
    return ('<h2>Sponsor tracks</h2><div class="tw"><table><tr><th>Track</th><th>Prize</th>'
            f'<th>Status</th><th>Evidence / what is missing</th></tr>{"".join(rows)}</table></div>')


def _submission_checklist_block(hackathon: dict | None) -> str:
    sc = (hackathon or {}).get("submission_checklist") or {}
    items = sc.get("items") or []
    if not items:
        return ""
    lis = "".join(f"<li>{html.escape(it)}</li>" for it in items)
    return f'<div class="card"><div class="k">Submission checklist</div><ul>{lis}</ul></div>'


def _what_we_read(report: dict) -> str:
    sources = (report.get("sources") or {}).get("sources") or []
    parts = []
    for src in sources:
        kind = src.get("kind")
        meta = src.get("meta") or {}
        if kind == "repo":
            parts.append("README")
        elif kind == "deck":
            n = meta.get("slides")
            parts.append(f"{n} slides" if n else "slides")
        elif kind == "page":
            title = meta.get("title")
            parts.append(f'page "{title}"' if title else "landing page")
        elif kind == "pitch":
            parts.append("pasted pitch text")
    return " + ".join(parts) if parts else "no sources read"


def _autonomy_stamp_label(autonomy: dict | None) -> str:
    if not autonomy:
        return "not run"
    return html.escape(f'{autonomy["k_hold"]} of {autonomy["n"]} hold ({autonomy["stamp"]})')


# --- human-facing stamp words (advisor dogfood #6) --------------------------------------------

_STAMP_WORDS = {
    "hackathon": {"contender": "Contender", "fixable_by_1830": "Fixable by 18:30",
                  "not_yet": "Not yet", "not_run": "Not run"},
    "business": {"ready_to_charge": "Ready to charge", "one_gap_away": "One gap away",
                 "not_yet": "Not a business yet", "not_run": "Not run"},
}
_AUTONOMY_WORDS = {"autonomous": "Autonomous", "human_in_the_loop": "Human in the loop",
                    "not_autonomous": "Not autonomous"}


def _stamp_word(kind: str, value: str) -> str:
    return _STAMP_WORDS.get(kind, {}).get(value, value)


def _autonomy_word(autonomy: dict | None) -> str:
    if not autonomy:
        return "Not run"
    word = _AUTONOMY_WORDS.get(autonomy["stamp"], autonomy["stamp"])
    return f'{word}, {autonomy["k_hold"]} of {autonomy["n"]}'


# --- sponsor table: rubric-sourced prize text, Terac/Stripe first, not_used collapsed ---------

def _sponsor_rubric_by_id() -> dict[str, dict]:
    try:
        rubric = hackathon.load_rubric()
    except Exception:
        return {}
    return {s.get("id"): s for s in rubric.get("sponsors", [])}


def _sponsor_track_prize(rubric_name: str) -> tuple[str, str]:
    """Rubric sponsor `name` bakes the prize text in after the last ", $..." (e.g. "Linq
    (iMessage/RCS/SMS API), $1,500 / $1,000"); split it into (track, prize). No embedded prize
    (Terac/Stripe: required rules, or partners with no track) -> prize "" ."""
    parts = re.split(r", (?=\$)", rubric_name, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return rubric_name.strip(), ""


def _short_name(rubric_name: str) -> str:
    track, _ = _sponsor_track_prize(rubric_name)
    return track.split(" (")[0].strip()


def _prize_amount(prize: str) -> float:
    m = re.search(r"\$([\d,]+)", prize)
    return float(m.group(1).replace(",", "")) if m else 0.0


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


def _autonomy_table(autonomy: dict | None) -> str:
    if not autonomy or not autonomy.get("items"):
        return "<p class='note'>autonomy rubric not run.</p>"
    rows = []
    for it in autonomy["items"]:
        row = (f"<tr><td><span class='id'>{html.escape(it['id'])}</span></td>"
               f"<td>{_pill(it['status'])}</td><td>{html.escape(it.get('plain', ''))}</td>"
               f"<td>{html.escape(it.get('fix', ''))}</td></tr>")
        if it["status"] in ("fail", "partial") and it.get("evidence_public"):
            e = it["evidence_public"][0]
            row += (f"<tr><td></td><td></td><td colspan='2' class='note'>"
                    f"{html.escape(e.get('what', ''))}: {html.escape(e.get('url', ''))}</td></tr>")
        rows.append(row)
    return (f'<p class="note">{html.escape(autonomy.get("note", ""))}</p>'
            '<div class="tw"><table><tr><th>Failure</th><th>Result</th><th>What it means</th><th>Fix</th></tr>'
            f'{"".join(rows)}</table></div>')


def _repo_advice(findings: list[dict]) -> str:
    tech = [f for f in findings if f.get("section") == "technical"]
    if not tech:
        return ""
    items = "".join(f"<li><span class='id'>{html.escape(f['id'])}</span> {html.escape(f['fix'])}</li>" for f in tech)
    return (f'<section class="page" data-page="PDF page 4">'
            f'<h2>From vibe-coded to an MVP</h2><p class="note">Repo supplied; agent-fixable first, same items are in agent.md.</p>'
            f'<ul>{items}</ul></section>')


_TEMPLATE_V2 = pathlib.Path(__file__).resolve().parents[1] / "docs" / "specs" / "report-template-v2.html"


def to_html_v2(report: dict) -> str | None:
    """The report design (docs/specs/report-template-v2.html, Jinja2 over report.json). None when the
    template or jinja2 is unavailable, so callers can fall back to the plain renderer."""
    try:
        import jinja2
        src = _TEMPLATE_V2.read_text()
    except Exception:
        return None
    env = jinja2.Environment(autoescape=True)
    try:
        return env.from_string(src).render(**report)
    except Exception as exc:
        try:
            store.event(report.get("job"), "report.template_error", {"error": str(exc)[:200]})
        except Exception:
            pass
        return None


def to_html_plain(report: dict) -> str:
    stamps = report["stamps"]
    comp = report["compounding"]
    top3 = "".join(f"<li>{html.escape(t)}</li>" for t in report["top3"])
    page1 = (
        '<section class="page" data-page="PDF page 1">'
        f'<div class="eyebrow">Reality Check, job <span class="id">{html.escape(report["job"])}</span></div>'
        f'<h1>{html.escape(str(report.get("project", "")))}</h1>'
        f'<div class="stamps"><span class="stamp warn">Hackathon: {html.escape(_stamp_word("hackathon", stamps["hackathon"]))}</span>'
        f'<span class="stamp warn">Autonomous: {html.escape(_autonomy_word(report.get("autonomy")))}</span>'
        f'<span class="stamp bad">Business: {html.escape(_stamp_word("business", stamps["business"]))}</span></div>'
        f'<div class="grid2"><div class="card"><div class="k">Do these before you submit</div><ol>{top3}</ol></div>'
        f'{_humans_card(report)}{_submission_checklist_block(report.get("hackathon"))}</div>'
        f'<p class="note">What we read: {html.escape(_what_we_read(report))}.</p>'
        f'{_sponsor_table(report.get("hackathon"))}'
        f'<div class="foot">Stamp rules: hackathon = contender/fixable_by_1830/not_yet by judging weight-3 items; '
        f'business = ready_to_charge/one_gap_away/not_yet by the four gaps. '
        f'{comp["n_reviewed"]} projects reviewed; this one ranks {comp.get("rank")}.</div>'
        '</section>'
    )
    page2 = ('<section class="page" data-page="PDF page 2"><h2>How to win this hackathon</h2>'
             f'{_judging_table(report.get("hackathon"))}<h3>Messaging</h3>{_messaging_list(report.get("hackathon"))}</section>')
    page3 = ('<section class="page" data-page="PDF page 3">'
             '<h2>Can this run autonomously? Seven ways agent-run companies fail</h2>'
             f'{_autonomy_table(report.get("autonomy"))}</section>')
    page4 = ('<section class="page" data-page="PDF page 4"><h2>Is it a business</h2>'
             f'{_business_gap_cards(report["findings"])}</section>')
    page5 = _repo_advice(report["findings"])
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
            'tr{page-break-inside:avoid}td:last-child{width:50%}'
            '.grid2{display:flex;gap:16px;flex-wrap:wrap}.card{background:#f2f0ea;padding:12px;flex:1}'
            '.id{font-family:monospace}pre{white-space:pre-wrap;background:#eee;padding:12px}'
            '@page{size:A4;margin:18mm}</style>'
            f'{page1}{page2}{page3}{page4}{page5}{last}'
            f'<section><h2>agent.md</h2><pre>{agent_md}</pre></section>')


def to_html(report: dict) -> str:
    return to_html_v2(report) or to_html_plain(report)


def to_pdf(report: dict) -> bytes | None:
    """WeasyPrint on the v2 design when the runtime has it (needs pango/cairo); else xhtml2pdf on
    the plain renderer; else None (caller serves HTML)."""
    html_v2 = to_html_v2(report)
    if html_v2:
        try:
            from weasyprint import HTML  # type: ignore
            data = HTML(string=html_v2).write_pdf()
            if data and data[:4] == b"%PDF":
                return data
        except Exception as exc:
            try:
                store.event(report.get("job"), "report.weasyprint_unavailable", {"error": str(exc)[:160]})
            except Exception:
                pass
    try:
        from xhtml2pdf import pisa
    except Exception:
        return None
    import io
    out = io.BytesIO()
    try:
        result = pisa.CreatePDF(io.StringIO(to_html_plain(report)), dest=out)
    except Exception:
        return None
    if result.err:
        return None
    data = out.getvalue()
    return data if data[:4] == b"%PDF" else None
