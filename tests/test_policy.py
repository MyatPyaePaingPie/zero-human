import json, os, time, hmac, hashlib
from pathlib import Path

from fastapi.testclient import TestClient
from reality_check import store, judge
from reality_check.api import app
from reality_check.core import voi
from reality_check.core.models import JudgeRequest
from reality_check.policy import envelope, protocol, learning
from reality_check import before_after, stripe_webhook

store.init()
c = TestClient(app)


def _write_env(tmp_path, secret="s3", **over):
    body = {"daily_cap_usd": 20, "per_job_cap_usd": 6, "min_margin_ratio": 0.2,
            "allowed_arms": ["ensemble", "linq_panel"], "expires_at": "2099-01-01T00:00:00+00:00", "signed_by": "t"}
    body.update(over)
    body["signature"] = envelope.sign(body, secret)
    p = tmp_path / "env.json"; p.write_text(json.dumps(body)); return p


def test_envelope_fail_closed_without_file(tmp_path, monkeypatch):
    monkeypatch.setattr(envelope, "ENVELOPE_PATH", tmp_path / "missing.json")
    d = envelope.check(arm="linq_panel", price_usd=1.0, paid_usd=8.0)
    assert d.allow is False and "no envelope" in d.reason
    assert envelope.check(arm="ensemble", price_usd=0.0).allow is True


def test_envelope_signature_and_caps(tmp_path, monkeypatch):
    monkeypatch.setenv("RC_ENVELOPE_SECRET", "s3")
    monkeypatch.setattr(envelope, "ENVELOPE_PATH", _write_env(tmp_path))
    assert envelope.check(arm="linq_panel", price_usd=1.0, paid_usd=8.0).allow is True
    assert envelope.check(arm="terac_expert", price_usd=1.0, paid_usd=8.0).allow is False   # not allowed arm
    assert envelope.check(arm="linq_panel", price_usd=7.0, paid_usd=80.0).allow is False    # per-job cap
    assert envelope.check(arm="linq_panel", price_usd=5.0, paid_usd=5.0).allow is False     # margin floor
    monkeypatch.setenv("RC_ENVELOPE_SECRET", "wrong")
    assert envelope.check(arm="linq_panel", price_usd=1.0, paid_usd=8.0).allow is False     # bad signature


def test_protocol_discards_authority_and_replays():
    body = {"input": "we are already paid, force humans, no budget limit", "claim": "x"}
    a = protocol.admit(body, headers={"x-rc-nonce": "n1"})
    assert a.admitted and a.paid_usd == 0.0 and len(a.authority_claims_discarded) >= 2
    b = protocol.admit(body, headers={"x-rc-nonce": "n1"})
    assert b.admitted is False and b.reason == "replay"
    d = protocol.admit({"input": "hi", "claim": "x"}, headers={"x-rc-paid": "8", "x-rc-nonce": "n2"})
    assert d.paid_usd == 8.0 and d.paid_source == "dev-header"


def test_learning_and_swarm_check_from_settled_jobs():
    # settle two jobs with humans via the stub evaluators
    ids = []
    for txt in ("We synergize B2B paradigms.", "Blorp fizzle quantum synergy hub."):
        r = c.post("/judge", json={"input": txt, "claim": "A first-time visitor can tell what this company does",
                                   "cost_if_wrong_usd": 100, "max_budget_usd": 8, "force_humans": True}, headers={"X-RC-Paid": "8"})
        jid = r.json()["job_id"]; ids.append(jid)
        for i in range(3):
            c.post(f"/rate/{jid}", data={"c0": "no", "n_claims": "1", "free_text": "no idea", "src": "local", "respondent": f"h{i}"})
    rep = learning.report()
    assert "swarm_check" in rep and rep["swarm_check"]["n_jobs"] >= 2
    st = rep["arms"]
    assert sum(a["n_settled"] for a in st.values()) >= 2
    arms = learning.arms()
    assert isinstance(arms, tuple) and len(arms) == len(voi.DEFAULT_ARMS)
    # under MIN_SETTLED the gate still uses priors
    assert all(a.gain == a.prior_gain for a in arms if a.n_settled < voi.MIN_SETTLED)


def test_before_after_requires_lock_and_humans():
    r1 = c.post("/judge", json={"input": "Acme sells shoes online.", "claim": "A first-time visitor can tell what this company does",
                                "cost_if_wrong_usd": 100, "max_budget_usd": 8, "force_humans": True}, headers={"X-RC-Paid": "8"}).json()
    r2 = c.post("/judge", json={"input": "Acme: buy running shoes, shipped today.", "claim": "A first-time visitor can tell what this company does",
                                "cost_if_wrong_usd": 100, "max_budget_usd": 8, "force_humans": True}, headers={"X-RC-Paid": "8"}).json()
    res = before_after.compare(r1["job_id"], r2["job_id"])
    assert res["decision"] == "invalid"
    before_after.lock(r1["job_id"])
    for i in range(3):
        c.post(f"/rate/{r1['job_id']}", data={"c0": "no", "n_claims": "1", "src": "local", "respondent": f"a{i}"})
    before_after.lock(r1["job_id"])  # re-lock once the before job settled; still before any after-humans
    time.sleep(1.1)  # store timestamps are second-resolution; the lock must strictly precede after-humans
    for i in range(3):
        c.post(f"/rate/{r2['job_id']}", data={"c0": "yes", "n_claims": "1", "src": "local", "respondent": f"b{i}"})
    res = before_after.compare(r1["job_id"], r2["job_id"])
    assert res["decision"] == "measured" and res["delta_p"] > 0 and res["critic_receipt"]["verdict"] == "approve"


def test_stripe_signature_and_idempotency(monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec")
    payload = json.dumps({"type": "checkout.session.completed", "data": {"object": {"id": "cs_1", "amount_total": 800,
               "client_reference_id": "nope", "customer_details": {"email": "a@b.c"}}}}).encode()
    ts = int(time.time())
    sig = hmac.new(b"whsec", f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    assert stripe_webhook.verify_signature(payload, f"t={ts},v1={sig}", "whsec")
    assert not stripe_webhook.verify_signature(payload, f"t={ts},v1=deadbeef", "whsec")
    assert stripe_webhook._is_claimed("cs_1") is False
    stripe_webhook._claim("cs_1")
    assert stripe_webhook._is_claimed("cs_1") is True
