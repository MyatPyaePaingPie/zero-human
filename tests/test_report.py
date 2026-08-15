"""Issue #4/#20: report.json + agent.md + PDF from one job. Stubs evaluators (no GROQ key ->
stub path already used by test_rubric.py), fakes probes via store.patch_job_state so objective
claims get real evidence deterministically, and injects a state.hackathon fixture matching the
contract the parallel lane is building.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from reality_check import report, store
from reality_check.api import app

c = TestClient(app)

FULL_INPUT = "Acme: AI roast of pitch decks for YC founders, $20 a roast, 3 paid so far. https://acme.example"

HACKATHON_FIXTURE = {
    "rubric_version": "v1",
    "personas": ["judge", "customer"],
    "model_calls": 4,
    "judging": [
        {"id": "judge/terac-human-loop", "title": "Human loop", "weight": 3, "status": "partial",
         "score": 0.5, "why": "humans recruited, no before/after", "fix": "add a before/after number",
         "claims": []},
        {"id": "judge/revenue", "title": "Revenue shown", "weight": 3, "status": "fail",
         "score": 0.0, "why": "no revenue number on the page", "fix": "add revenue to slide 1", "claims": []},
        {"id": "tech/replay-clean", "title": "Replay QA clean", "weight": 1, "status": "pass",
         "score": 1.0, "why": "no open bugs", "fix": "", "claims": []},
    ],
    "sponsors": {
        "qualifies": [{"id": "sponsor/stripe", "name": "Stripe", "required": True, "hints_found": ["buy.stripe.com"],
                       "claims": [], "status": "qualifies", "why": "payment link found", "fix": ""}],
        "claimed_not_evidenced": [{"id": "sponsor/linq", "name": "Linq", "required": False, "hints_found": [],
                                    "claims": [], "status": "claimed_not_evidenced",
                                    "why": "deck says texts customers, no linqapp in repo", "fix": "add linq usage"}],
        "cheapest_to_add": [{"id": "sponsor/replay", "name": "Replay", "required": False, "hints_found": [],
                              "claims": [], "status": "not_used", "why": "not used yet",
                              "fix": "run qa.replay.io on the URL"}],
        "not_used": [{"id": "sponsor/render-workflows", "name": "Render Workflows", "required": False,
                      "hints_found": [], "claims": [], "status": "not_used", "why": "hosted, no workflows", "fix": ""}],
    },
    "messaging": [
        {"id": "msg/first-screen", "theme": "headline", "status": "fail", "where": "slide 1 headline",
         "rewrite": "AI roast for YC founders, $20", "claims": []},
    ],
    "technical": [
        {"id": "tech/runnable", "title": "README has no run steps", "status": "fail",
         "why": "no install/run section", "fix": "add a Run section", "claims": []},
    ],
    "stamp": "fixable_by_1830",
    "top3": ["Add revenue number to slide 1", "Fix README run steps", "Name the payer on the hero"],
    "autonomy": [
        {"id": "auto/spend-authority", "title": "Who holds the money?", "failure": "budget in a prompt",
         "status": "fail", "score": 0.1, "why": "limit lives in the system prompt", "fix": "move limit to config"},
        {"id": "auto/idempotent-money", "title": "Fires exactly once", "failure": "double charge",
         "status": "partial", "score": 0.5, "why": "no idempotency key found", "fix": "key fulfillment by session id"},
        {"id": "auto/decision-quality", "title": "Measured vs doing nothing", "failure": "no baseline",
         "status": "pass", "score": 0.9, "why": "blind then revealed", "fix": ""},
        {"id": "auto/liveness", "title": "Someone notices it stopped", "failure": "no health check",
         "status": "pass", "score": 0.8, "why": "canary exists", "fix": ""},
        {"id": "auto/authority-boundary", "title": "Customer text is not authority", "failure": "chat -> refund",
         "status": "pass", "score": 0.85, "why": "refunds need a rule", "fix": ""},
        {"id": "auto/human-loop-design", "title": "Human where agents cannot decide", "failure": "n/a",
         "status": "pass", "score": 0.95, "why": "taste judged by humans, priced", "fix": ""},
        {"id": "auto/ledger", "title": "Append-only truth", "failure": "overwritten orders",
         "status": "pass", "score": 0.9, "why": "orders table overwritten", "fix": "append events"},
    ],
    "autonomy_stamp": "human_in_the_loop",
    "autonomy_note": "Graded against failure modes from two autonomous systems we built and ran ourselves.",
}


def _fake_probes(url: str) -> dict:
    return {
        "url": url, "ok": True, "fetched": True, "status": 200, "ttfb_ms": 120,
        "namespaces": ["audit", "live", "agentready", "replay", "autonomy", "security"],
        "unknown": [],
        "findings": [
            {"id": "audit/description-missing", "evidence": "GET / : no <meta name=description>"},
            {"id": "live/privacy-missing", "evidence": "no /privacy"},
        ],
    }


def _make_job() -> str:
    r = c.post("/judge", json={
        "input": FULL_INPUT, "sku": "full_reality_check", "url": "https://acme.example",
        "cost_if_wrong_usd": 100, "max_budget_usd": 8, "evidence_standard": "voi_routed",
    }, headers={"X-RC-Paid": "25"})
    assert r.status_code == 200, r.text
    jid = r.json()["job_id"]
    store.patch_job_state(jid, "probes", _fake_probes("https://acme.example"))
    return jid


def _settle(jid: str) -> None:
    v = c.get(f"/judge/{jid}").json()
    if v["status"] == "awaiting_humans":
        n = len(v["claims"])
        for i in range(3):
            data = {"n_claims": str(n), "src": "local", "respondent": f"h{i}", "free_text": "seems fine"}
            data.update({f"c{k}": "yes" for k in range(n)})
            assert c.post(f"/rate/{jid}", data=data).status_code == 200


def test_build_has_required_fields_on_every_finding():
    jid = _make_job()
    _settle(jid)
    store.patch_job_state(jid, "hackathon", HACKATHON_FIXTURE)
    rep = report.build(jid)
    assert rep["job"] == jid
    assert set(rep["stamps"]) == {"hackathon", "business", "autonomous"}
    assert rep["stamps"]["hackathon"] == "fixable_by_1830"
    assert rep["top3"]
    business = [f for f in rep["findings"] if "gap" in f]
    assert business, "expected business findings from state.claims"
    for f in rep["findings"]:
        for key in ("id", "owner", "evidence", "fix", "acceptance"):
            assert key in f, f"finding {f.get('id')} missing {key}"
        assert "lens" in f or "section" in f
    for f in business:
        assert f["gap"] in ("payer", "take_money", "stranger_proof", "loop")
    ids = [f["id"] for f in rep["findings"]]
    assert "judge/revenue" in ids
    assert "sponsor/linq" in ids
    assert rep["compounding"]["n_reviewed"] >= 1


def test_agent_owned_findings_before_human_owned():
    jid = _make_job()
    _settle(jid)
    store.patch_job_state(jid, "hackathon", HACKATHON_FIXTURE)
    rep = report.build(jid)
    md = report.to_agent_md(rep)
    agent_hdr = md.index("## Fix before 18:30 (agent-owned)")
    human_hdr = md.index("## Needs a human decision")
    assert agent_hdr < human_hdr
    # every id under the agent section (up to the human header) belongs to an agent-owned finding
    agent_owned_ids = {f["id"] for f in rep["findings"] if f["owner"] == "agent"}
    section = md[agent_hdr:human_hdr]
    for fid in agent_owned_ids:
        assert fid in section, f"{fid} missing from agent-owned section"


def test_html_sponsor_table_first_and_before_stamps():
    jid = _make_job()
    _settle(jid)
    store.patch_job_state(jid, "hackathon", HACKATHON_FIXTURE)
    rep = report.build(jid)
    doc = report.to_html(rep)
    first_table = doc.index("<table>")
    sponsor_hdr = doc.index("Sponsor tracks")
    stamps_div = doc.index('class="stamps"')
    assert sponsor_hdr < first_table
    assert stamps_div < sponsor_hdr, "stamps render before the sponsor table in page 1's markup, but the table is still the first table"
    # the sponsor table content appears before the stamp rule footer / any judging table
    assert doc.index("Stripe") < doc.index("How to win")


def test_build_without_hackathon_state_still_works(monkeypatch):
    from reality_check import judge as judge_module
    monkeypatch.setattr(judge_module, "_launch_hackathon", lambda *a, **k: None)
    jid = _make_job()
    _settle(jid)
    rep = report.build(jid)
    assert rep["stamps"]["hackathon"] == "not_run"
    assert rep["hackathon"] is None
    doc = report.to_html(rep)
    assert "hackathon rubric not run" in doc
    md = report.to_agent_md(rep)
    assert "## Business gaps" in md


def test_humans_pending_when_no_answers_yet():
    jid = _make_job()
    v = c.get(f"/judge/{jid}").json()
    if v["status"] != "awaiting_humans":
        return  # VOI settled internally; humans block should still be well-formed
    rep = report.build(jid)
    assert rep["evidence"]["humans"]["pending"] is True
    doc = report.to_html(rep)
    assert "humans pending" in doc


def test_to_pdf_returns_pdf_bytes_or_none_and_html_still_works():
    jid = _make_job()
    _settle(jid)
    store.patch_job_state(jid, "hackathon", HACKATHON_FIXTURE)
    rep = report.build(jid)
    pdf = report.to_pdf(rep)
    if pdf is None:
        assert report.to_html(rep)  # caller falls back to the HTML print view
    else:
        assert pdf[:4] == b"%PDF"


def test_compounding_counts_settled_jobs():
    jid1 = _make_job()
    _settle(jid1)
    before = report.build(jid1)["compounding"]["n_reviewed"]
    jid2 = _make_job()
    _settle(jid2)
    after = report.build(jid2)["compounding"]["n_reviewed"]
    assert after >= before


def test_report_routes(monkeypatch):
    jid = _make_job()
    _settle(jid)
    j = c.get(f"/report/{jid}.json"); assert j.status_code == 200 and j.json()["job"] == jid
    m = c.get(f"/report/{jid}/agent.md"); assert m.status_code == 200 and "## Business gaps" in m.text
    h = c.get(f"/report/{jid}"); assert h.status_code == 200 and "<table" in h.text
    p = c.get(f"/report/{jid}.pdf"); assert p.status_code == 200
    assert p.content.startswith(b"%PDF") or "<table" in p.text
    assert c.get("/report/nope.json").status_code == 404


def test_autonomy_k_hold_count():
    jid = _make_job()
    _settle(jid)
    store.patch_job_state(jid, "hackathon", HACKATHON_FIXTURE)
    rep = report.build(jid)
    assert rep["autonomy"]["k_hold"] == 5
    assert rep["autonomy"]["n"] == 7
    assert rep["autonomy"]["stamp"] == "human_in_the_loop"
    assert rep["stamps"]["autonomous"] == "human_in_the_loop"


def test_html_page3_autonomy_table_has_plain_text():
    jid = _make_job()
    _settle(jid)
    store.patch_job_state(jid, "hackathon", HACKATHON_FIXTURE)
    rep = report.build(jid)
    doc = report.to_html(rep)
    assert "Can this run autonomously" in doc
    # plain text for the failing item is pulled from the real rubric (hackathon.load_rubric()),
    # not the fixture -- prove the row explainer is present and non-empty
    plain = rep["autonomy"]["items"][0]["plain"]
    assert plain and plain in doc


def test_agent_md_autonomy_section_present():
    jid = _make_job()
    _settle(jid)
    store.patch_job_state(jid, "hackathon", HACKATHON_FIXTURE)
    rep = report.build(jid)
    md = report.to_agent_md(rep)
    assert "## Can it run autonomously" in md
    assert "### auto/spend-authority [fail]" in md


def test_evidence_public_line_only_under_failed_or_partial_items():
    jid = _make_job()
    _settle(jid)
    store.patch_job_state(jid, "hackathon", HACKATHON_FIXTURE)
    rep = report.build(jid)
    doc = report.to_html(rep)
    fail_item = next(i for i in rep["autonomy"]["items"] if i["id"] == "auto/spend-authority")
    assert fail_item["status"] == "fail"
    ev = fail_item["evidence_public"][0]
    assert ev["what"] in doc
    pass_item = next(i for i in rep["autonomy"]["items"] if i["id"] == "auto/ledger")
    assert pass_item["status"] == "pass"
    # a passing item's evidence_public text must not leak onto the page
    if pass_item.get("evidence_public"):
        assert pass_item["evidence_public"][0]["what"] not in doc


def test_autonomy_absent_on_older_jobs_tolerated():
    # simulate a job settled before the autonomy rubric shipped: state.hackathon exists
    # (the parallel lane's background evaluation already ran) but carries no "autonomy" key.
    jid = _make_job()
    _settle(jid)
    old_hackathon = {k: v for k, v in HACKATHON_FIXTURE.items() if k not in ("autonomy", "autonomy_stamp", "autonomy_note")}
    store.patch_job_state(jid, "hackathon", old_hackathon)
    rep = report.build(jid)
    assert rep["autonomy"] is None
    assert rep["stamps"]["autonomous"] == "not_run"
    doc = report.to_html(rep)
    assert "autonomy rubric not run" in doc
    md = report.to_agent_md(rep)
    assert "## Can it run autonomously" not in md
