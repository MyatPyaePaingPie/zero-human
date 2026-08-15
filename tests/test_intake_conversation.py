"""Conversation-first paid text intake. All access checks and model calls are injected; no network."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from reality_check import linq_client, store, textflow


REPO = "https://github.com/acme/rocket"
DECK = "https://docs.google.com/presentation/d/deck123/edit"
PAGE = "https://rocket.example"


def _setup(monkeypatch, checks=None):
    monkeypatch.delenv("RC_TEXT_FREE", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LINQ_API_KEY", raising=False)
    monkeypatch.setenv("RC_PAYLINK_DEFAULT", "https://buy.stripe.com/pay")
    checks = checks or {}

    def checker(kind, url):
        override = checks.get(url, {})
        return {"kind": kind, "url": url, "ok": True, "note": "",
                "title": {"repo": "acme/rocket", "deck": "Rocket deck", "page": "Rocket"}.get(kind),
                **override}

    monkeypatch.setattr(textflow, "access_checker", checker)


def _capture(monkeypatch):
    sent = []

    def send(to, text, *, job_id=None):
        sent.append({"to": to, "text": text, "job_id": job_id})

    monkeypatch.setattr(linq_client, "send", send)
    return sent


@pytest.mark.parametrize("order", [
    (DECK, REPO, PAGE),
    (REPO, PAGE, DECK),
    (PAGE, DECK, REPO),
])
def test_three_source_orders_share_job_and_done_pays_once(monkeypatch, order):
    _setup(monkeypatch)
    sent = _capture(monkeypatch)
    phone = "+1555200" + str(abs(hash(order)) % 100000).zfill(5)
    turns = [textflow.handle_text(phone, link) for link in order]
    done = textflow.handle_text(phone, "DONE")
    assert len({turn["job_id"] for turn in turns + [done]}) == 1
    job = store.get_job(done["job_id"])
    assert (job["request"]["repo"], job["request"]["deck"], job["request"]["url"]) == (REPO, DECK, PAGE)
    assert job["state"]["text_stage"] == "awaiting_payment"
    pays = [message for message in sent if "client_reference_id=" in message["text"]]
    assert len(pays) == 1
    assert "Reading 3 sources: repo, deck, page." in sent[-2]["text"]


def test_private_repo_is_not_attached_and_gets_fix_line(monkeypatch):
    _setup(monkeypatch, {REPO: {"ok": False, "note": "private or wrong", "title": None}})
    sent = _capture(monkeypatch)
    out = textflow.handle_text("+15552100001", REPO)
    job = store.get_job(out["job_id"])
    assert job["request"]["repo"] is None
    assert job["state"]["text_sources"][-1]["note"] == "private or wrong"
    assert "Make it public or paste your README text" in sent[-1]["text"]


def test_dead_page_is_not_attached(monkeypatch):
    _setup(monkeypatch, {PAGE: {"ok": False, "note": "does not load (status 500)", "title": None}})
    sent = _capture(monkeypatch)
    out = textflow.handle_text("+15552100002", PAGE)
    assert store.get_job(out["job_id"])["request"]["url"] is None
    assert "does not load (status 500)" in sent[-1]["text"]


def test_free_text_opens_job_and_appends_pitch(monkeypatch):
    _setup(monkeypatch)
    _capture(monkeypatch)
    first = textflow.handle_text("+15552100003", "A copilot that turns support calls into fixes")
    second = textflow.handle_text("+15552100003", "Built for small support teams")
    assert first["job_id"] == second["job_id"]
    pitch = store.get_job(first["job_id"])["request"]["input"]
    assert "turns support calls" in pitch and "Built for small support teams" in pitch


def test_price_is_stored_and_kept_in_pitch_context(monkeypatch):
    _setup(monkeypatch)
    _capture(monkeypatch)
    out = textflow.handle_text("+15552100004", "We charge $20 per month")
    job = store.get_job(out["job_id"])
    assert job["state"]["text_price"] == 20
    assert "$20" in job["request"]["input"]


def test_link_after_done_attaches_without_resending_payment(monkeypatch):
    _setup(monkeypatch)
    sent = _capture(monkeypatch)
    first = textflow.handle_text("+15552100005", REPO)
    textflow.handle_text("+15552100005", "DONE")
    after = textflow.handle_text("+15552100005", PAGE)
    assert after["job_id"] == first["job_id"]
    assert store.get_job(first["job_id"])["request"]["url"] == PAGE
    assert sent[-1]["text"] == "Added. Same payment link."
    assert sum("client_reference_id=" in message["text"] for message in sent) == 1


def test_pay_resends_same_job_link(monkeypatch):
    _setup(monkeypatch)
    sent = _capture(monkeypatch)
    first = textflow.handle_text("+15552100006", REPO)
    textflow.handle_text("+15552100006", "PAY")
    textflow.handle_text("+15552100006", "PAY")
    pays = [message["text"] for message in sent if "client_reference_id=" in message["text"]]
    assert len(pays) == 2
    assert all(first["job_id"] in pay for pay in pays)


def test_model_reply_is_used_when_composition_succeeds(monkeypatch):
    _setup(monkeypatch)
    sent = _capture(monkeypatch)
    monkeypatch.setattr(textflow, "compose_reply", lambda summary: "I opened acme/rocket. Any one is enough; more is better.")
    out = textflow.handle_text("+15552100007", REPO)
    assert sent[-1]["text"].startswith("I opened acme/rocket")
    event = next(e for e in store.events(200) if e["job_id"] == out["job_id"] and e["kind"] == "text.reply")
    assert event["payload"]["mode"] == "model"


def test_template_reply_is_used_when_composition_raises(monkeypatch):
    _setup(monkeypatch)
    sent = _capture(monkeypatch)

    def fail(_summary):
        raise RuntimeError("offline")

    monkeypatch.setattr(textflow, "compose_reply", fail)
    out = textflow.handle_text("+15552100008", REPO)
    assert sent[-1]["text"].startswith("Got it, saved.")
    event = next(e for e in store.events(200) if e["job_id"] == out["job_id"] and e["kind"] == "text.reply")
    assert event["payload"]["mode"] == "template"


def test_nudge_after_ten_minutes_only_once(monkeypatch):
    _setup(monkeypatch)
    sent = _capture(monkeypatch)
    out = textflow.handle_text("+15552100009", "One-line pitch")
    old = datetime.now(UTC) - timedelta(minutes=11)
    store.patch_job_state(out["job_id"], "text_last_message_at", old.isoformat())
    assert textflow.nudge_idle_threads(now=datetime.now(UTC)) == 1
    assert textflow.nudge_idle_threads(now=datetime.now(UTC) + timedelta(minutes=5)) == 0
    nudges = [m for m in sent if m["text"].startswith("Text DONE when")]
    assert len(nudges) == 1


def test_replies_never_echo_http_except_payment(monkeypatch):
    _setup(monkeypatch)
    sent = _capture(monkeypatch)
    monkeypatch.setattr(textflow, "compose_reply", lambda summary: "Opened it. See http://bad.example for details.")
    textflow.handle_text("+15552100010", PAGE)
    textflow.handle_text("+15552100010", "DONE")
    ordinary = [m["text"] for m in sent if "client_reference_id=" not in m["text"]]
    assert ordinary and all("http" not in text.lower() for text in ordinary)
