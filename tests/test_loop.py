import os
os.environ["RC_DB"] = "test_rc.db"
os.environ.pop("GROQ_API_KEY", None)
from pathlib import Path
Path("test_rc.db").unlink(missing_ok=True)

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
