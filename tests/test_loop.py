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
