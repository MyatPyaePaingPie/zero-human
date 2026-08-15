"""Issue #23: text intake. No network -- LINQ_API_KEY is never set here, so every send is a
dry ``linq.dry`` event (see linq_client.send); judge._launch_probes / _launch_hackathon are
monkeypatched to no-ops so job creation is instant and deterministic.
"""
from __future__ import annotations

from reality_check import judge, linq_client, store, textflow
from tests.test_report import HACKATHON_FIXTURE


def _no_launch(monkeypatch):
    monkeypatch.setattr(judge, "_launch_probes", lambda job_id, url: None)
    monkeypatch.setattr(judge, "_launch_hackathon", lambda job_id, text, has_repo: None)
    monkeypatch.setenv("RC_TEXT_FREE", "1")   # existing tests cover the free (room) path


def _dry_sends(job_id: str | None = None) -> list[dict]:
    evs = [e for e in store.events(200) if e["kind"] == "linq.dry"]
    return evs


def _inbound_event(phone: str, text: str) -> dict:
    return {"event_type": "message.received",
            "data": {"sender_handle": {"handle": phone}, "parts": [{"type": "text", "value": text}]}}


# ---- parse_links --------------------------------------------------------------------------

def test_parse_links_repo_deck_page():
    links = textflow.parse_links(
        "check it out https://github.com/acme/widget and slides https://docs.google.com/presentation/d/abc "
        "landing https://widget.example some more words"
    )
    assert links["repo"] == "https://github.com/acme/widget"
    assert links["deck"] == "https://docs.google.com/presentation/d/abc"
    assert links["url"] == "https://widget.example"
    assert "check it out" in links["pitch"] and "some more words" in links["pitch"]


def test_parse_links_page_only():
    links = textflow.parse_links("hey look at https://widget.example please")
    assert links["repo"] is None and links["deck"] is None
    assert links["url"] == "https://widget.example"


def test_parse_links_none():
    links = textflow.parse_links("hey I built a thing for founders")
    assert links["repo"] is None and links["deck"] is None and links["url"] is None
    assert links["pitch"] == "hey I built a thing for founders"


def test_parse_links_github_with_extra_words():
    links = textflow.parse_links("repo is https://github.com/acme/widget/tree/main check it out")
    assert links["repo"] == "https://github.com/acme/widget/tree/main"


# ---- first inbound: ack, job created ------------------------------------------------------

def test_first_inbound_with_links_creates_job_and_acks(monkeypatch):
    _no_launch(monkeypatch)
    phone = "+15551110001"
    event = _inbound_event(phone, "here's my project https://github.com/acme/widget and https://widget.example")
    result = linq_client.handle_inbound(event)
    assert "enrolled" not in result   # intake takes precedence; nobody is enrolled as a rater by default
    tf = result["textflow"]
    assert tf["action"] == "started"
    job = store.get_job(tf["job_id"])
    assert job is not None
    assert job["request"]["buyer_id"] == f"text:{linq_client.rater_id(phone)}"
    assert job["request"]["notify_phone"] == phone

    # WELCOME (new enrollment) and judge._notify's own settle text may also fire to this rater;
    # what matters is exactly one dry send that is our ack, with no link in it.
    sends = _dry_sends()
    ours = [e for e in sends if e["payload"]["to"] == linq_client.rater_id(phone)]
    acks = [e for e in ours if e["payload"]["text"] == textflow.ACK_LINE[:80]]
    assert len(acks) == 1, "exactly one dry send matching the ack"
    assert "http" not in acks[0]["payload"]["text"]


def test_inbound_without_links_and_no_thread_asks(monkeypatch):
    _no_launch(monkeypatch)
    phone = "+15551110002"
    event = _inbound_event(phone, "hey I built a cool thing")
    result = linq_client.handle_inbound(event)
    tf = result["textflow"]
    assert tf["action"] == "ask"
    sends = [e for e in _dry_sends() if e["payload"]["to"] == linq_client.rater_id(phone)]
    asks = [e for e in sends if e["payload"]["text"] == textflow.ASK_LINE[:80]]
    assert len(asks) == 1


# ---- on_report_ready ------------------------------------------------------------------------

def test_on_report_ready_sends_once(monkeypatch):
    _no_launch(monkeypatch)
    phone = "+15551110003"
    result = textflow.start_from_text(phone, "https://github.com/acme/widget https://widget.example")
    job_id = result["job_id"]

    store.patch_job_state(job_id, "hackathon", HACKATHON_FIXTURE)
    textflow.on_report_ready(job_id)
    # no humans yet: NO report, one status text ("graded, humans reading"), never a model-only report
    assert not [e for e in store.events(200) if e["job_id"] == job_id and e["kind"] == "text.result_sent"]
    assert len([e for e in store.events(200) if e["job_id"] == job_id and e["kind"] == "text.graded_sent"]) == 1
    textflow.on_humans_timeout(job_id)
    assert len([e for e in store.events(200) if e["job_id"] == job_id and e["kind"] == "text.wait_sent"]) == 1
    assert not [e for e in store.events(200) if e["job_id"] == job_id and e["kind"] == "text.result_sent"]
    # humans land: the final report goes out once, with the humans line inside
    store.add_human_answer(job_id, "local", "r1", True, "makes sense", claim_idx=0)
    textflow.on_humans_ready(job_id)
    sent_events = [e for e in store.events(200) if e["job_id"] == job_id and e["kind"] == "text.result_sent"]
    assert len(sent_events) == 1, "one send recorded for this job"
    # payload text in the dry event is truncated to 80 chars by linq_client.send; fetch the
    # full message from the compose function directly to check its shape
    job = store.get_job(job_id)
    from reality_check import report
    full_text = textflow._compose_result(job, report.build(job_id))
    assert f"/report/{job_id}.pdf" in full_text
    assert "agent.md" in full_text
    assert "Do first:" in full_text

    # second call: idempotent, no new send recorded
    textflow.on_report_ready(job_id)
    sent_events_after = [e for e in store.events(200) if e["job_id"] == job_id and e["kind"] == "text.result_sent"]
    assert len(sent_events_after) == 1


def test_rerun_creates_new_job_with_before_job_id(monkeypatch):
    _no_launch(monkeypatch)
    phone = "+15551110004"
    first = textflow.start_from_text(phone, "https://github.com/acme/widget https://widget.example")
    event = _inbound_event(phone, "RERUN")
    result = linq_client.handle_inbound(event)
    tf = result["textflow"]
    assert tf["action"] == "rerun"
    assert tf["before_job_id"] == first["job_id"]
    new_job = store.get_job(tf["job_id"])
    assert new_job["request"]["before_job_id"] == first["job_id"]
    assert new_job["request"]["repo"] == first["links"]["repo"]
    assert new_job["request"]["url"] == first["links"]["url"]


# ---- on_humans_ready ------------------------------------------------------------------------

def test_on_humans_ready_two_answers(monkeypatch):
    _no_launch(monkeypatch)
    phone = "+15551110005"
    result = textflow.start_from_text(phone, "https://widget.example")
    job_id = result["job_id"]
    store.add_human_answer(job_id, "local", "r1", True, "could tell what it does", claim_idx=0)
    store.add_human_answer(job_id, "local", "r2", False, "confusing headline", claim_idx=0)

    textflow.on_humans_ready(job_id)
    assert not [e for e in _dry_sends() if e["job_id"] == job_id], "no rubric yet: nothing sent"
    store.patch_job_state(job_id, "hackathon", HACKATHON_FIXTURE)
    textflow.on_humans_ready(job_id)
    sends = [e for e in _dry_sends() if e["job_id"] == job_id]
    assert sends, "expected the final send with the humans line"
    from reality_check import store as store_mod  # noqa: F401
    job = store.get_job(job_id)
    # recompose to check the full (untruncated) text
    n = len(store.human_answers(job_id))
    assert n == 2
    full = textflow._compose_humans(job_id)
    assert "2 strangers" in full and "of 2" in full


def test_humans_keyword_before_answers_says_not_in_yet(monkeypatch):
    _no_launch(monkeypatch)
    phone = "+15551110006"
    textflow.start_from_text(phone, "https://widget.example")
    event = _inbound_event(phone, "HUMANS")
    result = linq_client.handle_inbound(event)
    assert result["textflow"]["action"] == "humans_not_ready"
    sends = [e for e in _dry_sends() if e["payload"]["to"] == linq_client.rater_id(phone)]
    not_in_yet = [e for e in sends if "Not in yet" in e["payload"]["text"]]
    assert len(not_in_yet) == 1


def test_paid_text_flow_creates_pending_order_and_sends_paylink_second(monkeypatch):
    """Default (RC_TEXT_FREE unset): job waits in pending_payment; ack has no link; second text
    carries the Payment Link with client_reference_id; the poller's complete_session starts it."""
    monkeypatch.setattr(judge, "_launch_probes", lambda job_id, url: None)
    monkeypatch.setattr(judge, "_launch_hackathon", lambda job_id, text, has_repo: None)
    monkeypatch.delenv("RC_TEXT_FREE", raising=False)
    monkeypatch.setenv("RC_PAYLINK_DEFAULT", "https://buy.stripe.com/test_link")
    n0 = len(_dry_sends())
    out = linq_client.handle_inbound(_inbound_event("+15550001111", "https://github.com/acme/rockets"))
    tf = out["textflow"]
    assert tf["action"] == "pending_payment"
    job = store.get_job(tf["job_id"])
    assert job["status"] == "pending_payment" and job["buyer_id"].startswith("text:")
    texts = [e["payload"]["text"] for e in _dry_sends() if e.get("job_id") == tf["job_id"]]
    assert texts, "no dry sends recorded for the job"
    # welcome (new rater) + ack + pay link: the FIRST job-related text has no link, the pay text does
    acks = [t for t in texts if t.startswith("Got it")]
    assert acks and "http" not in acks[0]
    assert any("buy.stripe.com/test_link" in t for t in texts)   # dry events keep the first 80 chars
    created = [e for e in store.events(200) if e["kind"] == "order.created" and e["job_id"] == tf["job_id"]]
    assert created and created[0]["payload"]["pay_url"].endswith("?client_reference_id=" + tf["job_id"])
    # payment lands: complete_session starts the job with revenue
    from reality_check import stripe_webhook
    res = stripe_webhook.complete_session({"id": "cs_text_" + tf["job_id"], "payment_status": "paid", "amount_total": 800,
                                           "client_reference_id": tf["job_id"], "customer_details": {}})
    assert res.get("started") == tf["job_id"]
    assert store.get_job(tf["job_id"])["status"] in ("settled", "awaiting_humans", "evaluating")
    with store.conn() as c:
        row = c.execute("SELECT amount_usd FROM ledger WHERE job_id=? AND kind='revenue'", (tf["job_id"],)).fetchone()
    assert row and abs(row["amount_usd"] - 8.0) < 1e-6


def test_paid_session_auto_launches_terac_when_switch_on(monkeypatch):
    from reality_check import judge as judge_module, panels, stripe_webhook, store
    from reality_check.policy import envelope as env_mod
    monkeypatch.setattr(judge_module, "_launch_probes", lambda job_id, url: None)
    monkeypatch.setattr(judge_module, "_launch_hackathon", lambda job_id, text, has_repo: None)
    monkeypatch.delenv("RC_TEXT_FREE", raising=False)
    monkeypatch.setenv("RC_PAYLINK_DEFAULT", "https://buy.stripe.com/test_link")
    monkeypatch.setenv("RC_TERAC_AUTO", "1")
    monkeypatch.setattr(env_mod, "gate_panel_launch", lambda job_id, arm, price, paid: price <= 20)
    launched = {}
    class FakeTerac:
        name = "terac"
        def launch(self, job_id, question, input_text, n, approve=None):
            launched["n"] = n; assert approve(18.0)
            return panels.PanelHandle("terac", "opp_auto", f"http://x/rate/{job_id}", n, 18.0)
    monkeypatch.setitem(panels.REGISTRY, "terac", FakeTerac())
    out = linq_client.handle_inbound(_inbound_event("+15550009999", "https://github.com/acme/rockets"))
    jid = out["textflow"]["job_id"]
    res = stripe_webhook.complete_session({"id": "cs_auto_" + jid, "payment_status": "paid", "amount_total": 0,
                                           "client_reference_id": jid, "customer_details": {}})
    assert res.get("started") == jid and res.get("humans", {}).get("launched") is True
    assert launched["n"] == 3 and store.get_job(jid)["state"]["panel"]["external_id"] == "opp_auto"
