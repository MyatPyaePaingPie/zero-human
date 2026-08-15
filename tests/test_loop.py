from fastapi.testclient import TestClient
from reality_check.api import app
from reality_check.core import voi

c = TestClient(app)


def test_voi_fail_closed_when_confident():
    d = voi.decide(p_internal=0.95, dissent=0.0, cost_if_wrong_usd=50, max_budget_usd=8)
    assert d.buy is False


def test_voi_buys_when_uncertain_and_stakes_high():
    d = voi.decide(p_internal=0.55, dissent=0.6, cost_if_wrong_usd=50, max_budget_usd=8)
    assert d.buy is True and d.arm in ("linq_panel", "terac_general")


def test_voi_no_buy_when_stakes_tiny():
    d = voi.decide(p_internal=0.55, dissent=0.6, cost_if_wrong_usd=0.5, max_budget_usd=8)
    assert d.buy is False


def test_round_trip_humans_settle():
    r = c.post("/judge", json={"input": "We synergize B2B paradigms.", "claim": "A first-time visitor can tell what this company does",
                               "cost_if_wrong_usd": 100, "max_budget_usd": 8}, headers={"X-RC-Paid": "8"})
    assert r.status_code == 200, r.text
    v = r.json(); jid = v["job_id"]
    assert v["status"] in ("awaiting_humans", "settled")
    if v["status"] == "awaiting_humans":
        for i in range(3):
            rr = c.post(f"/rate/{jid}", data={"c0": "no", "n_claims": "1", "free_text": "no idea", "src": "local", "respondent": f"h{i}"})
            assert rr.status_code == 200
        v = c.get(f"/judge/{jid}").json()
        assert v["status"] == "settled" and v["n_humans"] == 3 and v["verdict"] == "no"
    assert c.get("/ledger").json()["revenue_usd"] == 8.0
    assert c.get("/").status_code == 200


def test_demand_check_rubric_multi_claim():
    r = c.post("/judge", json={"input": "Acme sells AI roast of pitch decks to YC founders for $20; 3 paid so far.", "sku": "demand_check",
                               "force_humans": True, "cost_if_wrong_usd": 100}, headers={"X-RC-Paid": "10"})
    assert r.status_code == 200, r.text
    v = r.json(); jid = v["job_id"]
    assert len(v["claims"]) == 6 and v["status"] == "awaiting_humans"
    for i in range(3):
        data = {"n_claims": "6", "src": "local", "respondent": f"d{i}", "free_text": "my cofounder would pay"}
        data.update({f"c{k}": ("yes" if k != 5 else "no") for k in range(6)})
        assert c.post(f"/rate/{jid}", data=data).status_code == 200
    v = c.get(f"/judge/{jid}").json()
    assert v["status"] == "settled" and v["n_humans"] == 3
    assert [x["verdict"] for x in v["claims"]] == ["yes"] * 5 + ["no"] and v["verdict"] == "no"
    assert c.get(f"/rate/{jid}").status_code == 200


def test_intake_verified_autonomous():
    r = c.post("/intake", json={"team": "acme", "live_url": "https://acme.example", "claims": ["No human approves any purchase", "Agent hires humans via Terac on its own"], "invariants": ["Spend never exceeds $20/day"]}, headers={"X-RC-Paid": "10"})
    assert r.status_code == 200, r.text
    v = r.json()
    assert len(v["claims"]) == 2 and v["status"] == "awaiting_humans"


def test_rate_page_stamps_uuid_and_dupes_are_not_counted():
    r = c.post("/judge", json={"input": "Foo bar", "claim": "It is clear", "force_humans": True}, headers={"X-RC-Paid": "5"})
    jid = r.json()["job_id"]
    page = c.get(f"/rate/{jid}").text
    import re
    m = re.search(r'name=respondent value="([0-9a-f]{12})"', page)
    assert m, "rate page must stamp a respondent id"
    rid = m.group(1)
    a = c.post(f"/rate/{jid}", data={"c0": "yes", "n_claims": "1", "src": "local", "respondent": rid})
    b = c.post(f"/rate/{jid}", data={"c0": "yes", "n_claims": "1", "src": "local", "respondent": rid})
    assert "Thanks" in a.text and "Already counted" in b.text
    # blank respondent (old client) still gets a fresh id, not the shared IP
    d1 = c.post(f"/rate/{jid}", data={"c0": "no", "n_claims": "1", "src": "local", "respondent": ""})
    d2 = c.post(f"/rate/{jid}", data={"c0": "no", "n_claims": "1", "src": "local", "respondent": ""})
    assert "Thanks" in d1.text and "Thanks" in d2.text
    assert c.get(f"/judge/{jid}").json()["n_humans"] == 3


def test_resettle_until_target_then_freeze():
    r = c.post("/judge", json={"input": "Foo", "claim": "It is clear", "force_humans": True}, headers={"X-RC-Paid": "5"})
    jid = r.json()["job_id"]
    for i, ans in enumerate(["yes", "yes", "no", "no", "no"]):
        c.post(f"/rate/{jid}", data={"c0": ans, "n_claims": "1", "src": "local", "respondent": f"z{i}"})
        v = c.get(f"/judge/{jid}").json()
        if i >= 2:
            assert v["status"] == "settled"
    assert v["verdict"] == "no" and v["n_humans"] == 5
    c.post(f"/rate/{jid}", data={"c0": "yes", "n_claims": "1", "src": "local", "respondent": "z9"})
    assert c.get(f"/judge/{jid}").json()["n_humans"] == 6  # counted, but settlement frozen at 5


def test_deadline_blocks_slow_arms():
    d = voi.decide(p_internal=0.55, dissent=0.6, cost_if_wrong_usd=100, max_budget_usd=30, max_latency_s=600)
    assert d.arm in (None, "ensemble", "linq_panel")


def test_unknown_persona_is_422():
    r = c.post("/judge", json={"input": "x", "claim": "y", "personas": ["nope"]})
    assert r.status_code == 422


def test_stripe_complete_session_idempotent():
    from reality_check import stripe_webhook
    o = c.post("/order", json={"input": "Landing page copy", "claim": "Clear", "sku": "reality_check"}).json()
    jid = o["job_id"]
    sess = {"id": "cs_test_1", "payment_status": "paid", "amount_total": 800, "client_reference_id": jid, "customer_details": {"email": "a@b.c"}}
    r1 = stripe_webhook.complete_session(sess); r2 = stripe_webhook.complete_session(dict(sess))
    assert r1.get("started") == jid and r2 == {"duplicate": "cs_test_1"}
    assert c.get(f"/order/{jid}").json()["revenue_usd"] == 8.0


def test_timeout_settles_model_only(monkeypatch):
    from reality_check import judge as J
    r = c.post("/judge", json={"input": "Foo", "claim": "It is clear", "force_humans": True}, headers={"X-RC-Paid": "5"})
    jid = r.json()["job_id"]
    assert r.json()["status"] == "awaiting_humans"
    monkeypatch.setattr(J, "HUMAN_TIMEOUT_S", -1.0)
    v = c.get(f"/judge/{jid}").json()
    assert v["status"] == "settled" and "did not answer in time" in v["summary"]


def test_stripe_failed_start_is_not_claimed(monkeypatch):
    from reality_check import stripe_webhook, judge as J
    o = c.post("/order", json={"input": "x", "claim": "y"}).json(); jid = o["job_id"]
    sess = {"id": "cs_test_fail", "payment_status": "paid", "amount_total": 800, "client_reference_id": jid}
    def boom(*a, **k): raise RuntimeError("evaluators down")
    monkeypatch.setattr(J, "start", boom)
    import pytest
    with pytest.raises(RuntimeError):
        stripe_webhook.complete_session(sess)
    monkeypatch.undo()
    assert stripe_webhook.complete_session(sess).get("started") == jid  # retried, not duplicate
    assert stripe_webhook.complete_session(sess) == {"duplicate": "cs_test_fail"}
    assert stripe_webhook.complete_session({"id": "cs_x", "amount_total": 100}) == {"unpaid": "cs_x"}


def test_intake_without_replay_key_is_dry():
    r = c.post("/intake", json={"team": "acme", "live_url": "https://example.com", "claims": ["The checkout works without a human"]}, headers={"X-RC-Paid": "10"})
    assert r.status_code == 200, r.text
    jid = r.json()["job_id"]
    kinds = [e["kind"] for e in c.get("/events?limit=50").json() if e["job_id"] == jid]
    assert "replay.dry" in kinds and "Replay" not in r.json()["summary"]


def test_standard_is_a_floor_not_a_bypass():
    r = c.post("/judge", json={"input": "Crystal clear text about socks.", "claim": "It is clear", "sku": "reality_check",
                               "cost_if_wrong_usd": 1}, headers={"X-RC-Paid": "8"}).json()
    v = r["voi"]
    assert r["status"] == "awaiting_humans" and v["buy"] and v["arm"] == "linq_panel" and "standard human_backed" in v["reason"]
    r2 = c.post("/judge", json={"input": "Crystal clear text about socks.", "claim": "It is clear", "sku": "reality_check",
                                "evidence_standard": "voi_routed", "cost_if_wrong_usd": 1}).json()
    assert r2["voi"]["buy"] is False and r2["status"] == "settled"


def test_before_after_refuses_shared_respondents():
    b = c.post("/judge", json={"input": "v1 copy", "claim": "It is clear", "sku": "reality_check"}, headers={"X-RC-Paid": "8"}).json()
    for i in range(3):
        c.post(f"/rate/{b['job_id']}", data={"c0": "no", "n_claims": "1", "src": "local", "respondent": f"p{i}"})
    c.post(f"/before_after/lock/{b['job_id']}")
    a = c.post("/judge", json={"input": "v2 copy", "claim": "It is clear", "sku": "reality_check", "before_job_id": b["job_id"]}, headers={"X-RC-Paid": "8"}).json()
    rej = c.post(f"/rate/{a['job_id']}", data={"c0": "yes", "n_claims": "1", "src": "local", "respondent": "p0"})
    assert "previous version" in rej.text
    for i in range(3):
        c.post(f"/rate/{a['job_id']}", data={"c0": "yes", "n_claims": "1", "src": "local", "respondent": f"q{i}"})
    cmp_ = c.get(f"/before_after/{b['job_id']}/{a['job_id']}").json()
    assert cmp_["decision"] == "measured" and cmp_["locked_at"] and cmp_["delta_p"] > 0


def test_full_reality_check_bundle_lenses():
    r = c.post("/judge", json={"input": "Acme: AI roast of pitch decks for YC founders, $20, 3 paid.", "sku": "full_reality_check",
                               "extra_claims": ["A user can pay and receive the roast without a human"]}, headers={"X-RC-Paid": "25"})
    assert r.status_code == 200, r.text
    v = r.json(); jid = v["job_id"]
    # the claim list is lenses.run_order() now, not a hand-built clarity+demand list (issue #2/#18)
    from reality_check import lenses as L
    seen = [x["lens"] for x in v["claims"]]
    assert seen == [l for _c, l, _i in L.claims_for_run(extra_claims=["A user can pay and receive the roast without a human"])]
    assert v["status"] == "awaiting_humans"
    page = c.get(f"/verdict/{jid}").text
    assert "clarity" in page and "demand" in page and "autonomy" in page and "viability" in page
    # (the page's own "economics" money block is not a lens block; disabled lenses have no claims)
    assert "economics" not in seen and "projections" not in seen and "competition" not in seen


def test_unpaid_request_cannot_spend_and_revenue_once():
    from reality_check import store
    from reality_check.policy import envelope
    assert envelope.check(arm="linq_panel", price_usd=1.0, paid_usd=0.0).allow is False
    assert store.ledger_add_once("dup-job", "revenue", 8.0, "x") is True
    assert store.ledger_add_once("dup-job", "revenue", 8.0, "x") is False


def test_anonymous_rater_gets_sticky_identity():
    from fastapi.testclient import TestClient
    from reality_check.api import app
    cc = TestClient(app)
    a = cc.post("/judge", json={"input": "v1", "claim": "It is clear", "sku": "reality_check"}, headers={"X-RC-Paid": "8"}).json()
    import re
    p1 = cc.get(f"/rate/{a['job_id']}").text; r1 = re.search(r'name=respondent value="([0-9a-f]{12})"', p1).group(1)
    b = cc.post("/judge", json={"input": "v2", "claim": "It is clear", "sku": "reality_check", "before_job_id": a["job_id"]}, headers={"X-RC-Paid": "8"}).json()
    p2 = cc.get(f"/rate/{b['job_id']}").text; r2 = re.search(r'name=respondent value="([0-9a-f]{12})"', p2).group(1)
    assert r1 == r2  # same phone, same identity across jobs


def test_rating_closed_until_job_starts():
    o = c.post("/order", json={"input": "x", "claim": "y"}).json()
    assert c.get(f"/rate/{o['job_id']}").status_code == 409
    assert c.post(f"/rate/{o['job_id']}", data={"c0": "yes", "n_claims": "1"}).status_code == 409


def test_linq_webhook_enrolls_and_panel_falls_back_when_dry(monkeypatch):
    import base64, json, time, hmac, hashlib
    from reality_check import linq_client, store
    secret_raw = b"0123456789abcdef0123456789abcdef"
    secret = "whsec_" + base64.b64encode(secret_raw).decode()
    monkeypatch.setenv("LINQ_WEBHOOK_SECRET", secret)
    ev = {"event_type": "message.received", "data": {"sender_handle": {"handle": "+15550001111"}, "parts": [{"type": "text", "value": "RATE"}]}}
    body = json.dumps(ev).encode(); ts = str(int(time.time())); mid = "msg_1"
    sig = "v1," + base64.b64encode(hmac.new(secret_raw, f"{mid}.{ts}.".encode() + body, hashlib.sha256).digest()).decode()
    r = c.post("/linq/webhook", content=body, headers={"webhook-id": mid, "webhook-timestamp": ts, "webhook-signature": sig, "content-type": "application/json"})
    assert r.status_code == 200 and r.json().get("enrolled")
    assert c.post("/linq/webhook", content=body, headers={"webhook-id": mid, "webhook-timestamp": ts, "webhook-signature": "v1,bad"}).status_code == 400
    assert store.raters_count() == 1
    # no LINQ_API_KEY in tests: panel recruits nobody -> judge falls back to local page, job still awaits humans
    v = c.post("/judge", json={"input": "x", "claim": "It is clear", "sku": "reality_check", "notify_phone": "+15550002222"}, headers={"X-RC-Paid": "8"}).json()
    assert v["status"] == "awaiting_humans"
    kinds = [e["kind"] for e in c.get("/events?limit=80").json() if e["job_id"] == v["job_id"]]
    assert "linq.nobody" in kinds and "panel.fallback" in kinds


def test_sweep_never_spends():
    r = c.post("/sweep?sync=true", json={"items": [{"name": "Foo", "tagline": "Bar for devs", "description": "We synergize.", "url": "https://x.y"}]})
    assert r.status_code == 200, r.text
    row = r.json()[0]
    assert row["voi"] is None or row["voi"]["buy"] is False or "envelope denied" in row["voi"]["reason"]
    v = c.get(f"/judge/{row['job_id']}").json()
    assert v["status"] == "settled" and v["evidence_cost_usd"] < 0.01
    assert c.get("/sweep").status_code == 200 and "Foo" in c.get("/sweep").text
