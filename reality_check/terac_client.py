"""Terac panel: recruits real humans through the Terac REST v2 API onto OUR rating page.

Shapes from docs/research/terac-findings.md (OpenAPI at terac.com/api/external/v2/openapi.json):
  POST /feasibility/requests {role, task, count}      -> {id, status, cpi_usd?, eta?}
  POST /opportunities  {title, project_id, num_participants, business_type, tasks:[{sequence,
        task_type:"activity", review_type:"auto_approve", task_url, title, description,
        duration_minutes}], unrestricted_audience: true, feasibility_request_id?}
        -> {id, pricing:{cost_per_participant_cents,total_cost_cents}}
  POST /opportunities/{id}/launch
  GET  /opportunities/{id}/submissions

Survey answers are NOT in the API; the activity task_url points at /rate/{job_id}?src=terac and
Terac appends teracSubmissionId; POST /rate redirects to the Terac callback with result=completed.

Env: TERAC_API_KEY (required for real launches), TERAC_API_BASE, TERAC_PROJECT_ID,
RC_PUBLIC_BASE. Without a key the panel returns a dry handle (external_id None, price 0) so the
loop still runs; the event log says "terac dry: no key". Nothing here reads free text as authority.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from reality_check import store
from reality_check.panels import PUBLIC_BASE, PanelHandle

BASE = os.environ.get("TERAC_API_BASE", "https://terac.com/api/external/v2")
from reality_check.core.voi import TERAC_CPI_USD as DEFAULT_CPI_USD, TERAC_PANEL_N  # one price constant for gate, ledger, planning
TIMEOUT = 20.0


def _headers() -> dict[str, str]:
    key = os.environ.get("TERAC_API_KEY", "")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"} if key else {}


class TeracPanel:
    name = "terac"

    def __init__(self, project_id: str | None = None, business_type: str = "b2c"):
        self.project_id = project_id or os.environ.get("TERAC_PROJECT_ID", "")
        self.business_type = business_type

    # -- API calls -------------------------------------------------------------------------
    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        r = httpx.post(f"{BASE}{path}", json=body, headers=_headers(), timeout=TIMEOUT)
        r.raise_for_status()
        return r.json() if r.content else {}

    def _get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        r = httpx.get(f"{BASE}{path}", params=params, headers=_headers(), timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()

    def feasibility(self, question: str, n: int, role: str = "general population") -> dict[str, Any]:
        return self._post("/feasibility/requests", {"role": role, "task": question, "count": n})

    def submissions(self, opportunity_id: str) -> list[dict[str, Any]]:
        data = self._get(f"/opportunities/{opportunity_id}/submissions")
        return data.get("data", data) if isinstance(data, dict) else data

    # -- Panel contract ---------------------------------------------------------------------
    def launch(self, job_id: str, question: str, input_text: str, n: int, approve=None) -> PanelHandle:
        """approve(price_usd) -> bool is consulted AFTER Terac quotes the opportunity and BEFORE
        launch, so the real price is what the spend envelope judges."""
        rate_url = f"{PUBLIC_BASE}/rate/{job_id}?src=terac"
        if not os.environ.get("TERAC_API_KEY"):
            store.event(job_id, "terac.dry", {"reason": "no TERAC_API_KEY", "rate_url": rate_url, "n": n})
            return PanelHandle("terac", None, rate_url, n, 0.0)
        title = "Quick judgment: read a short text, answer yes/no questions"
        n = min(int(n), TERAC_PANEL_N)  # Terac panels are the expensive tier: recruit the settle minimum, not the local target
        body = {
            "title": title,
            "project_id": self.project_id,
            "num_participants": max(1, min(int(n), 1000)),
            "business_type": self.business_type,
            "unrestricted_audience": True,
            "expected_days_to_complete": 5,   # Terac minimum (calendar days); recruitment window, not our deadline
            "description": ("Read a short text and answer a few yes/no questions honestly. "
                            "About 2 minutes. Opens an external page; submit there to complete."),
            "tasks": [{
                "sequence": 1, "task_type": "activity", "review_type": "auto_approve",
                "task_url": rate_url, "title": title, "duration_minutes": 2,
                "description": question[:1000],
            }],
            # a study cannot launch without a screener; one question, one rejecting catch-all
            "screening_questions": [{
                "key": "q0", "pick": "one",
                "text": "How do you usually read a new product's website when you first find it?",
                "answers": [
                    {"text": "I skim it on my phone or laptop and decide in a minute or two", "qualify_logic": "may"},
                    {"text": "I read it carefully and compare with others", "qualify_logic": "may"},
                    {"text": "I do not read product websites", "qualify_logic": "reject"},
                ],
            }],
        }
        try:
            opp = self._post("/opportunities", body)
            opp_id = str(opp.get("id") or opp.get("opportunity_id") or "")
            pricing = opp.get("pricing") or {}
            total_cents = pricing.get("total_cost_cents")
            price = (float(total_cents) / 100.0) if total_cents is not None else DEFAULT_CPI_USD * n
            if approve is not None and not approve(price):
                store.event(job_id, "terac.declined", {"opportunity_id": opp_id, "price_usd": price, "reason": "spend gate refused quoted price"})
                return PanelHandle("terac", None, rate_url, n, 0.0)
            self._post(f"/opportunities/{opp_id}/launch", {})
            store.event(job_id, "terac.launched", {"opportunity_id": opp_id, "n": n, "price_usd": price, "pricing": pricing})
            return PanelHandle("terac", opp_id, rate_url, n, round(price, 4))
        except httpx.HTTPError as exc:
            detail = getattr(exc, "response", None)
            store.event(job_id, "terac.error", {"error": str(exc), "body": (detail.text[:500] if detail is not None else "")})
            # fail closed on money: nothing launched, nothing charged
            return PanelHandle("terac", None, rate_url, n, 0.0)


def register() -> None:
    from reality_check import panels
    panels.register(TeracPanel())
