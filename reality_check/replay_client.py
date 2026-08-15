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


FLOW_HINTS = ("can ", "user ", "customer ", "visitor ", "submit", "pay", "checkout", "sign", "log in", "login",
              "click", "form", "button", "flow", "works", "loads", "renders", "sends", "receives", "without a human")


def is_flow_claim(claim: str) -> bool:
    """Objective, journey-testable claims (user flows) go to Replay; squishy ones stay with humans."""
    c = claim.lower()
    return any(h in c for h in FLOW_HINTS)


def launch(job_id: str, target_url: str, name: str, *, design_document: str = "", claims: list[str] | None = None) -> dict[str, Any] | None:
    """Open a Replay project on the target URL, testing the product against what the team SAYS it
    does (design_document = claims + invariants + pitch), and one agent-driven journey per flow
    claim so claim verdicts get objective evidence. Returns the handle stored in job state."""
    if not enabled():
        store.event(job_id, "replay.dry", {"reason": "no REPLAY_API_KEY", "target_url": target_url})
        return None
    try:
        body = {"name": name[:80], "target_url": target_url,
                "instructions": "Audit this app against the design document: test every claim it makes, note anything that requires a human where the claim says it does not."}
        if design_document:
            body["design_document"] = design_document[:20000]
        r = httpx.post(f"{BASE}/projects", json=body, headers=_headers(), timeout=TIMEOUT)
        r.raise_for_status()
        d = r.json()
        handle = {"project_id": str(d.get("id") or d.get("project_id")), "exploration_id": d.get("exploration_id"),
                  "url": d.get("url"), "target_url": target_url, "launched_at": store.now(), "polled_at": None, "bugs": None,
                  "journeys": {}, "versions": []}
        for i, claim in enumerate(claims or []):
            if not is_flow_claim(claim):
                continue
            try:
                jr = httpx.post(f"{BASE}/projects/{handle['project_id']}/journeys",
                                json={"name": f"claim {i+1}"[:60], "description": claim[:2000],
                                      "instructions": "Carry out this claim end to end as a real user. Report whether it holds without human intervention."},
                                headers=_headers(), timeout=TIMEOUT)
                jr.raise_for_status()
                jd = jr.json()
                handle["journeys"][str(i)] = {"journey_id": str(jd.get("id") or jd.get("journey_id")), "claim": claim, "result": None, "bugs": []}
            except httpx.HTTPError as exc:
                store.event(job_id, "replay.journey.error", {"claim_idx": i, "error": str(exc)[:200]})
        if PRICE_USD:
            store.ledger_add(job_id, "cost.replay_qa", PRICE_USD, f"replay project {handle['project_id']}")
        store.event(job_id, "replay.launched", {k: v for k, v in handle.items() if k != "journeys"} | {"journeys": len(handle["journeys"])})
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
                     "open": sum(1 for b in items if str(b.get("status", "open")).lower() not in ("fixed", "resolved", "closed")),
                     "top": [{"title": str(b.get("title", ""))[:120], "severity": b.get("severity"), "status": b.get("status")} for b in items[:5]]},
        })
        for j in (handle.get("journeys") or {}).values():
            try:
                jr = httpx.get(f"{BASE}/journeys/{j['journey_id']}", headers=_headers(), timeout=TIMEOUT)
                jr.raise_for_status()
                jd = jr.json()
                jbugs = jd.get("bugs") or []
                runs = jd.get("test_runs") or jd.get("versions") or []
                last = runs[-1] if isinstance(runs, list) and runs else {}
                j["bugs"] = [str(b.get("id")) for b in jbugs if isinstance(b, dict)][:20]
                j["result"] = (str(last.get("status") or last.get("result") or ("failed" if jbugs else "unknown"))).lower()
            except httpx.HTTPError as exc:
                j["result"] = j.get("result") or "unknown"
                store.event(job_id, "replay.journey.error", {"journey_id": j["journey_id"], "error": str(exc)[:200]})
        store.event(job_id, "replay.findings", handle["bugs"] | {"journeys": {k: v["result"] for k, v in (handle.get("journeys") or {}).items()}})
    except httpx.HTTPError as exc:
        store.event(job_id, "replay.error", {"error": str(exc)[:300]})
    return handle


def record_version(job_id: str, handle: dict[str, Any], *, git_sha: str, branch: str, deployed_url: str | None, change: str) -> dict[str, Any] | None:
    """Team redeployed: tell Replay to re-test. Snapshot bug counts so before/after has an
    objective delta next to the human one."""
    if not enabled():
        return None
    try:
        r = httpx.post(f"{BASE}/projects/{handle['project_id']}/versions",
                       json={"git_sha": git_sha, "branch_name": branch, "deployed_url": deployed_url or handle["target_url"], "change_description": change[:2000]},
                       headers=_headers(), timeout=TIMEOUT)
        r.raise_for_status()
        snap = {"at": store.now(), "git_sha": git_sha, "bugs_before": (handle.get("bugs") or {}).get("count"),
                "open_before": (handle.get("bugs") or {}).get("open"), "version": r.json()}
        handle.setdefault("versions", []).append(snap)
        handle["polled_at"] = None  # force a refresh on next verdict()
        store.event(job_id, "replay.version", snap)
        return snap
    except httpx.HTTPError as exc:
        store.event(job_id, "replay.error", {"error": str(exc)[:300]})
        return None


def objective_delta(handle: dict[str, Any] | None) -> dict[str, Any] | None:
    """bugs_before (at last recorded version) vs bugs now. None until a version was recorded."""
    if not handle or not handle.get("versions") or not handle.get("bugs"):
        return None
    v = handle["versions"][-1]
    now_open = handle["bugs"].get("open", handle["bugs"]["count"])
    return {"git_sha": v["git_sha"], "open_before": v.get("open_before"), "open_after": now_open,
            "resolved": (v.get("open_before") or 0) - now_open if v.get("open_before") is not None else None}


def summary_line(handle: dict[str, Any] | None) -> str:
    if not handle:
        return ""
    b = handle.get("bugs")
    if not b:
        return "Replay QA exploration running (objective evidence pending)."
    sev = ", ".join(f"{v} {k}" for k, v in sorted(b["by_severity"].items()))
    js = handle.get("journeys") or {}
    jl = ""
    if js:
        done = {k: v["result"] for k, v in js.items() if v.get("result") and v["result"] != "unknown"}
        jl = f" Flow claims: {len(done)}/{len(js)} tested" + (", " + ", ".join(f"#{int(k)+1} {r}" for k, r in sorted(done.items())) if done else "") + "."
    d = objective_delta(handle)
    dl = f" Since redeploy {d['git_sha'][:7]}: open bugs {d['open_before']} -> {d['open_after']}." if d and d.get("open_before") is not None else ""
    return f"Replay QA found {b['count']} bug(s){' (' + sev + ')' if sev else ''} on the live URL.{jl}{dl}"
