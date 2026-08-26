"""Issue #22: the three endpoints the storefront reads had no coverage. These pin the response
contract (key names and shapes), which is what breaks a separate-origin Lovable page silently:
/summary is its ONE call, /skus is the price list, /raters is the "humans are real" counter.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from reality_check import lenses, linq_client, skus, store
from reality_check.api import app

c = TestClient(app)


def test_skus_is_the_price_list_lenses_owns():
    body = c.get("/skus").json()
    assert body.keys() == skus.SKUS.keys()
    assert body["reality_check"]["price_usd"] == 8.0 and body["full_reality_check"]["price_usd"] == 25.0
    full = body["full_reality_check"]
    assert full["claims"] == [cl.text for cl, _l, _i in lenses.claims_for_run()]  # derived, not hardcoded
    assert full["lenses"] and len(full["lenses"]) == len(full["claims"])


def test_raters_counts_opted_in_and_reports_linq_state():
    body = c.get("/raters").json()
    assert body == {"opted_in": store.raters_count(), "linq_enabled": linq_client.enabled()}
    assert isinstance(body["opted_in"], int) and body["linq_enabled"] is False  # no LINQ_API_KEY in tests


def test_summary_is_one_call_and_survives_a_pending_order():
    """/summary fans out over every recent job, including pay-first jobs that have no verdict yet:
    a pending /order must not 500 the storefront."""
    pending = c.post("/order", json={"input": "x", "claim": "y", "sku": "reality_check"}).json()["job_id"]
    settled = c.post("/judge", json={"input": "Acme sells socks for runners, $12 a pair.", "claim": "It is clear",
                                     "sku": "reality_check", "evidence_standard": "voi_routed",
                                     "max_budget_usd": 0}).json()["job_id"]

    s = c.get("/summary").json()
    assert s.keys() == {"money", "counts", "learning", "skus", "pay_links", "recent"}
    assert {"revenue_usd", "cost_usd", "margin_usd", "by_kind"} <= set(s["money"])
    assert s["counts"]["jobs"] == len(s["recent"]) >= 2
    assert isinstance(s["counts"]["by_status"], dict) and isinstance(s["counts"]["humans"], int)
    assert s["counts"]["voi_bought"] >= 0 and s["counts"]["voi_declined"] >= 0
    assert set(s["learning"]) == {"swarm_check", "arms"}
    assert "custom" not in s["skus"]  # the catalogue the storefront shows, not the internal preset
    assert all({"price_usd", "evidence_standard", "claims"} <= set(v) for v in s["skus"].values())
    assert set(s["pay_links"]) == {"reality_check", "full_reality_check"}

    rows = {r["job_id"]: r for r in s["recent"]}
    assert {pending, settled} <= rows.keys()
    assert rows[pending]["status"] == "pending_payment" and rows[settled]["sku"] == "reality_check"
    assert set(rows[settled]) == {"job_id", "status", "verdict", "p", "n_humans", "sku", "voi",
                                  "revenue_usd", "evidence_cost_usd", "summary"}
