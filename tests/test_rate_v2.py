"""The v2 human brief page (docs/specs/human-brief.md): what a Terac respondent sees on
/rate/{job} for a full_reality_check job, and how their six answers settle the job.

No network: sources.normalize is stubbed, probes and the hackathon thread are no-ops.
"""
from fastapi.testclient import TestClient

from reality_check import judge, report, store
from reality_check.api import app

c = TestClient(app)

PITCH = "Acme: AI roast of pitch decks for YC founders, $20 a roast, 3 paid so far."

PAGE_SOURCE = {"kind": "page", "ref": "https://acme.example", "live_url": "https://acme.example",
               "text": "Roast my deck\nGet a brutal read on your pitch deck in ten minutes. Start a roast. $20 per deck.",
               "meta": {"title": "Acme - roast my deck"}}
REPO_SOURCE = {"kind": "repo", "ref": "https://github.com/acme/roast", "live_url": None,
               "text": "repo: acme/roast\n\n--- README ---\n# Roast My Deck\n\nA command line tool that reads your pitch deck and tells you what a skeptical investor would say.\n\n## Install\nbrew install roast",
               "meta": {"title": "acme/roast"}}
PITCH_SOURCE = {"kind": "pitch", "ref": "pasted", "live_url": None, "text": PITCH, "meta": {}}


def _norm(sources, live_url=None):
    return {"text": "\n\n".join(s["text"] for s in sources), "live_url": live_url,
            "source_kinds": [s["kind"] for s in sources], "sources": sources,
            "primary_kind": sources[0]["kind"], "warnings": []}


def _quiet(monkeypatch, sources, live_url=None):
    from reality_check import sources as sources_mod
    monkeypatch.setattr(sources_mod, "normalize", lambda **kw: _norm(sources, live_url))
    monkeypatch.setattr(judge, "_launch_probes", lambda *a, **k: None)
    monkeypatch.setattr(judge, "_launch_hackathon", lambda *a, **k: None)


def _make_job(monkeypatch, sources, live_url=None) -> str:
    _quiet(monkeypatch, sources, live_url)
    r = c.post("/judge", json={"input": PITCH, "sku": "full_reality_check", "repo": "https://github.com/acme/roast",
                              "url": live_url, "cost_if_wrong_usd": 100, "max_budget_usd": 8},
               headers={"X-RC-Paid": "25"})
    assert r.status_code == 200, r.text
    return r.json()["job_id"]


V2_BODY = {"q1_what": "a tool that roasts your pitch deck for founders", "q2_pay": "yes",
           "q2_why": "I would try it before a real pitch", "q2_price_guess": "$10",
           "q3_who": "a friend who just raised a seed", "q4_stopper": "no idea who is behind it",
           "q5_ai_effect": "less", "q5_why": "I want a person to complain to",
           "q6_real": "weekend", "q6_why": "no team page"}


def _post(jid, respondent, **over):
    body = dict(V2_BODY, src="terac", respondent=respondent, teracSubmissionId=respondent, panel_version="v2")
    body.update(over)
    return c.post(f"/rate/{jid}", data=body, follow_redirects=False)


def test_v2_page_renders_the_brief(monkeypatch):
    jid = _make_job(monkeypatch, [REPO_SOURCE, PAGE_SOURCE, PITCH_SOURCE], live_url="https://acme.example")
    page = c.get(f"/rate/{jid}?teracSubmissionId=abc").text
    assert "their landing page" in page
    assert "https://acme.example" in page and "Open the full landing page" in page
    assert "their README" not in page          # a page exists, so the README is not the stimulus
    for name in ("q1_what", "q2_pay", "q2_why", "q2_price_guess", "q3_who", "q4_stopper",
                 "q5_ai_effect", "q5_why", "q6_real", "q6_why"):
        assert f'name="{name}"' in page or f"name={name}" in page, name
    assert 'name="teracSubmissionId" value="abc"' in page
    assert "n_claims" not in page              # no v1 claim list
    assert "Inter" not in page
    assert store.get_job(jid)["state"]["panel_version"] == "v2"
    assert "$20" in page  # the price line


def test_repo_only_job_falls_back_to_the_readme(monkeypatch):
    jid = _make_job(monkeypatch, [REPO_SOURCE, PITCH_SOURCE])
    page = c.get(f"/rate/{jid}").text
    assert "their README" in page and "their landing page" not in page
    assert "Roast My Deck" in page and "skeptical investor" in page


def test_submit_stores_the_brief_and_redirects_to_terac(monkeypatch):
    jid = _make_job(monkeypatch, [PAGE_SOURCE, PITCH_SOURCE], live_url="https://acme.example")
    r = _post(jid, "sub_1")
    assert r.status_code == 303
    assert r.headers["location"] == "https://terac.com/api/external/callback?teracSubmissionId=sub_1&result=completed"
    briefs = store.human_briefs(jid)
    assert len(briefs) == 1
    a = briefs[0]["answers"]
    assert a["q2_pay"] is True and a["q1_what"] == V2_BODY["q1_what"] and a["q5_ai_effect"] == "less"
    assert briefs[0]["terac_submission_id"] == "sub_1"
    # a repeat submission from the same respondent is not counted twice
    assert _post(jid, "sub_1").status_code == 303
    assert len(store.human_briefs(jid)) == 1


def test_three_respondents_settle_the_job_and_the_report_carries_the_brief(monkeypatch):
    jid = _make_job(monkeypatch, [PAGE_SOURCE, PITCH_SOURCE], live_url="https://acme.example")
    assert c.get(f"/judge/{jid}").json()["status"] == "awaiting_humans"
    _post(jid, "s1")
    _post(jid, "s2")
    _post(jid, "s3", q2_pay="no", q1_what="no idea", q3_who="no one", q5_ai_effect="more")
    v = c.get(f"/judge/{jid}").json()
    assert v["status"] == "settled" and v["n_humans"] == 3
    b = report.build(jid)["evidence"]["humans"]["brief"]
    assert b["n"] == 3 and b["would_pay"] == 2 and b["knows_someone"] == 2
    assert b["ai_effect"] == {"more": 1, "less": 2, "same": 0}
    assert b["real_vs_weekend"] == {"real": 0, "weekend": 3}
    assert b["price_guesses"] == ["$10", "$10", "$10"] and b["panel_version"] == "v2"
    assert [q["q"] for q in b["quotes"]] == ["q1_what", "q4_stopper"]
    assert b["settled_at"] and b["timed_out"] is False
    # the claim-level mapping: clarity claim 0 saw 2 yes / 1 no
    c0 = [a for a in store.human_answers(jid) if a["claim_idx"] == 0]
    assert len(c0) == 3 and sum(1 for a in c0 if a["answer_yes"]) == 2


def test_non_full_job_keeps_the_v1_page():
    r = c.post("/judge", json={"input": "We synergize B2B paradigms.", "claim": "It is clear",
                               "sku": "reality_check", "cost_if_wrong_usd": 100, "max_budget_usd": 8},
               headers={"X-RC-Paid": "8"})
    jid = r.json()["job_id"]
    page = c.get(f"/rate/{jid}").text
    assert "n_claims" in page and "q1_what" not in page


def test_deck_slide_one_is_labelled_and_linked(monkeypatch):
    deck = {"kind": "deck", "ref": "https://pitch.com/acme", "live_url": "https://pitch.com/acme",
            "text": "--- slide 1 ---\nRoast My Deck\nBrutal feedback in ten minutes\n--- slide 2 ---\nMarket size: huge",
            "meta": {"slides": 2}}
    jid = _make_job(monkeypatch, [deck, PITCH_SOURCE])
    page = c.get(f"/rate/{jid}").text
    assert "their first slide" in page and "Open the deck" in page
    assert "Brutal feedback" in page and "Market size" not in page  # slide 1 only


def test_pitch_plus_url_job_reads_the_landing_page_at_render_time(monkeypatch):
    """judge._resolve_sources does not read a page when a pitch was pasted; the panel still shows it."""
    monkeypatch.setattr(judge, "_launch_probes", lambda *a, **k: None)
    monkeypatch.setattr(judge, "_launch_hackathon", lambda *a, **k: None)
    r = c.post("/judge", json={"input": PITCH, "sku": "full_reality_check", "url": "https://acme.example",
                              "cost_if_wrong_usd": 100, "max_budget_usd": 8}, headers={"X-RC-Paid": "25"})
    jid = r.json()["job_id"]
    assert store.get_job(jid)["state"].get("sources") is None

    from reality_check import sources as sources_mod
    monkeypatch.setattr(sources_mod, "read_page",
                        lambda url, **kw: sources_mod.Source(kind="page", ref=url, text=PAGE_SOURCE["text"],
                                                             live_url=url, meta=PAGE_SOURCE["meta"]))
    page = c.get(f"/rate/{jid}").text
    assert "their landing page" in page and "brutal read" in page
    assert store.get_job(jid)["state"]["sources"]["sources"][0]["kind"] == "page"  # cached for the next respondent


def test_unreadable_page_still_gets_a_link(monkeypatch):
    monkeypatch.setattr(judge, "_launch_probes", lambda *a, **k: None)
    monkeypatch.setattr(judge, "_launch_hackathon", lambda *a, **k: None)
    r = c.post("/judge", json={"input": PITCH, "sku": "full_reality_check", "url": "https://blocked.example",
                              "cost_if_wrong_usd": 100, "max_budget_usd": 8}, headers={"X-RC-Paid": "25"})
    jid = r.json()["job_id"]
    from reality_check import sources as sources_mod
    monkeypatch.setattr(sources_mod, "read_page",
                        lambda url, **kw: sources_mod.Source(kind="page", ref=url, text="", live_url=None,
                                                             meta={"error": "blocked_host"}))
    page = c.get(f"/rate/{jid}").text
    assert "their landing page" in page and "https://blocked.example" in page
