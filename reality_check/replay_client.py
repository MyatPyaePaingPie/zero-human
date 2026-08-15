"""Replay QA as an OBJECTIVE evidence source (sponsor: qa.replay.io, REST v1, bearer lqa_ token).

Humans answer subjective claims ("a stranger understands this"); Replay answers objective ones
("the form submits", "no broken flows") by crawling the live URL and filing bugs with root causes.
Used on verified_autonomous intake, where the team hands us a live URL: we open a Replay project
against it, then fold its bug counts into the verdict summary and the job state (`replay`).

Shapes from https://qa.replay.io/api/v1/openapi.json (read 2026-08-15):
  POST /api/v1/projects {name, target_url}      -> {id, exploration_id, url}
  GET  /api/v1/projects/{id}/status              -> counts (explorations, journeys, test runs, bugs)
  GET  /api/v1/projects/{id}/bugs                -> list of bugs (title, severity, status, ...)

Env: REPLAY_API_KEY (absent = event replay.dry, nothing launched), REPLAY_API_BASE,
REPLAY_PRICE_USD (planning cost written to the ledger; 0 during the hackathon).
Fails closed: any HTTP error records replay.error and the job proceeds without Replay evidence.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from reality_check import store

BASE = os.environ.get("REPLAY_API_BASE", "https://qa.replay.io/api/v1")
PRICE_USD = float(os.environ.get("REPLAY_PRICE_USD", "0"))
POLL_MIN_S = 60
TIMEOUT = 20.0


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {os.environ.get('REPLAY_API_KEY', '')}", "Content-Type": "application/json"}


def enabled() -> bool:
    return bool(os.environ.get("REPLAY_API_KEY"))


def launch(job_id: str, target_url: str, name: str) -> dict[str, Any] | None:
    """Open a Replay project on the target URL. Returns the handle stored in job state, or None."""
    if not enabled():
        store.event(job_id, "replay.dry", {"reason": "no REPLAY_API_KEY", "target_url": target_url})
        return None
    try:
        r = httpx.post(f"{BASE}/projects", json={"name": name[:80], "target_url": target_url}, headers=_headers(), timeout=TIMEOUT)
        r.raise_for_status()
        d = r.json()
        handle = {"project_id": str(d.get("id") or d.get("project_id")), "exploration_id": d.get("exploration_id"),
                  "url": d.get("url"), "target_url": target_url, "launched_at": store.now(), "polled_at": None, "bugs": None}
        if PRICE_USD:
            store.ledger_add(job_id, "cost.replay_qa", PRICE_USD, f"replay project {handle['project_id']}")
        store.event(job_id, "replay.launched", handle)
        return handle
    except httpx.HTTPError as exc:
        resp = getattr(exc, "response", None)
        store.event(job_id, "replay.error", {"error": str(exc), "body": (resp.text[:400] if resp is not None else "")})
        return None


def _age_s(iso: str | None) -> float:
    from datetime import datetime, timezone
    if not iso:
        return 1e9
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)).total_seconds()
    except ValueError:
        return 1e9


def refresh(job_id: str, handle: dict[str, Any]) -> dict[str, Any]:
    """Pull status + bugs at most every POLL_MIN_S. Mutates and returns the handle."""
    if not enabled() or _age_s(handle.get("polled_at")) < POLL_MIN_S:
        return handle
    pid = handle["project_id"]
    try:
        st = httpx.get(f"{BASE}/projects/{pid}/status", headers=_headers(), timeout=TIMEOUT)
        st.raise_for_status()
        bugs = httpx.get(f"{BASE}/projects/{pid}/bugs", headers=_headers(), timeout=TIMEOUT)
        bugs.raise_for_status()
        raw = bugs.json()
        items = raw.get("bugs") or raw.get("data") or raw if isinstance(raw, (list, dict)) else []
        if isinstance(items, dict):
            items = list(items.values())
        sev: dict[str, int] = {}
        for b in items:
            sev[str(b.get("severity", "unknown")).lower()] = sev.get(str(b.get("severity", "unknown")).lower(), 0) + 1
        handle.update({
            "polled_at": store.now(), "status": st.json(),
            "bugs": {"count": len(items), "by_severity": sev,
                     "top": [{"title": str(b.get("title", ""))[:120], "severity": b.get("severity"), "status": b.get("status")} for b in items[:5]]},
        })
        store.event(job_id, "replay.findings", handle["bugs"])
    except httpx.HTTPError as exc:
        store.event(job_id, "replay.error", {"error": str(exc)[:300]})
    return handle


def summary_line(handle: dict[str, Any] | None) -> str:
    if not handle:
        return ""
    b = handle.get("bugs")
    if not b:
        return "Replay QA exploration running (objective evidence pending)."
    sev = ", ".join(f"{v} {k}" for k, v in sorted(b["by_severity"].items()))
    return f"Replay QA found {b['count']} bug(s){' (' + sev + ')' if sev else ''} on the live URL."
