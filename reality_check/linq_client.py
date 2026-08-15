"""Linq: the fast human tier (minutes) and the delivery channel (iMessage/RCS/SMS).

Sponsor API: https://api.linqapp.com/api/partner/v3, bearer LINQ_API_KEY (docs.linqapp.com).
Inbound-first by Linq's own guidance: raters JOIN by texting our line; we never cold-text.

- POST /linq/webhook (Standard Webhooks HMAC, secret LINQ_WEBHOOK_SECRET): message.received ->
  "STOP" opts the sender out; anything else enrolls them as a rater and gets a one-line welcome.
- LinqPanel.launch(job, question, text, n): texts the /rate link to the n least-recently-used
  opted-in raters (src=linq&r=<hash of phone>, so the same person keeps one identity across
  jobs); returns a handle with external_id "linq:<n_sent>" or None when nobody could be sent
  (judge then falls back to the local page). Price 0: carrier cost is noise at this scale.
- notify_verdict(job_id): if the buyer gave notify_phone, text them the verdict line + link.
Fails closed on every HTTP error: event logged, nothing else changes.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from typing import Any

import httpx

from reality_check import store
from reality_check.panels import PUBLIC_BASE, PanelHandle

BASE = os.environ.get("LINQ_API_BASE", "https://api.linqapp.com/api/partner/v3")
TIMEOUT = 20.0
WELCOME = ("You're on the Reality Check rater list. When someone pays for a check we'll text you a 2-minute "
           "yes/no page. Reply STOP any time to leave.")


def enabled() -> bool:
    return bool(os.environ.get("LINQ_API_KEY"))


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {os.environ.get('LINQ_API_KEY', '')}", "Content-Type": "application/json"}


def rater_id(phone: str) -> str:
    return "lq" + hashlib.sha256(phone.encode()).hexdigest()[:10]


def send(to: str, text: str, *, job_id: str | None = None) -> dict[str, Any] | None:
    if not enabled():
        store.event(job_id, "linq.dry", {"to": rater_id(to), "text": text[:80]})
        return None
    try:
        r = httpx.post(f"{BASE}/messages", json={"to": [to], "message": {"parts": [{"type": "text", "value": text}]}},
                       headers=_headers(), timeout=TIMEOUT)
        r.raise_for_status()
        d = r.json()
        store.event(job_id, "linq.sent", {"to": rater_id(to), "service": d.get("service"), "chat_id": d.get("chat_id")})
        return d
    except httpx.HTTPError as exc:
        resp = getattr(exc, "response", None)
        store.event(job_id, "linq.error", {"to": rater_id(to), "error": str(exc)[:200], "body": (resp.text[:200] if resp is not None else "")})
        return None


# ---- raters (opt-in list) --------------------------------------------------------------------
def enroll(phone: str) -> bool:
    return store.rater_upsert(phone, opted_out=False)


def opt_out(phone: str) -> None:
    store.rater_upsert(phone, opted_out=True)


def verify_signature(headers: dict[str, str], body: bytes, secret: str, now: float | None = None) -> bool:
    """Standard Webhooks: HMAC-SHA256(base64decode(secret sans whsec_), "{id}.{ts}.{body}") base64, 5-min window."""
    h = {k.lower(): v for k, v in headers.items()}
    mid, ts, sig = h.get("webhook-id", ""), h.get("webhook-timestamp", ""), h.get("webhook-signature", "")
    if not (mid and ts and sig and secret):
        return False
    try:
        if abs((now or time.time()) - int(ts)) > 300:
            return False
        key = base64.b64decode(secret.split("whsec_", 1)[-1])
    except (ValueError, TypeError):
        return False
    expected = base64.b64encode(hmac.new(key, f"{mid}.{ts}.".encode() + body, hashlib.sha256).digest()).decode()
    return any(hmac.compare_digest(expected, part.split(",", 1)[1]) for part in sig.split() if part.startswith("v1,"))


def handle_inbound(event: dict[str, Any]) -> dict[str, Any]:
    if event.get("event_type") != "message.received":
        return {"ignored": event.get("event_type")}
    data = event.get("data") or {}
    phone = ((data.get("sender_handle") or {}).get("handle")) or ""
    text = " ".join(p.get("value", "") for p in data.get("parts", []) if p.get("type") == "text").strip()
    if not phone:
        return {"ignored": "no sender"}
    if text.upper() in ("STOP", "UNSUBSCRIBE", "QUIT", "END", "CANCEL"):
        opt_out(phone)
        store.event(None, "linq.optout", {"rater": rater_id(phone)})
        return {"opted_out": rater_id(phone)}
    new = enroll(phone)
    store.event(None, "linq.enrolled", {"rater": rater_id(phone), "new": new})
    if new:
        send(phone, WELCOME)
    from reality_check import textflow  # local: avoid a module-load cycle with judge/report
    result = textflow.handle_text(phone, text)
    return {"enrolled": rater_id(phone), "new": new, "textflow": result}


# ---- panel ------------------------------------------------------------------------------------
class LinqPanel:
    name = "linq"

    def launch(self, job_id: str, question: str, input_text: str, n: int, approve=None) -> PanelHandle:
        raters = store.raters_pick(n) if enabled() else []
        sent = 0
        for ph in raters:
            url = f"{PUBLIC_BASE}/rate/{job_id}?src=linq&r={rater_id(ph)}"
            if send(ph, f"Reality Check: 2 minutes, honest yes/no. {url}", job_id=job_id):
                store.rater_touch(ph)
                sent += 1
        rate_url = f"{PUBLIC_BASE}/rate/{job_id}?src=linq"
        if not sent:
            store.event(job_id, "linq.nobody", {"raters_available": len(raters), "enabled": enabled()})
            return PanelHandle("linq", None, rate_url, n, 0.0)
        return PanelHandle("linq", f"linq:{sent}", rate_url, sent, 0.0)


def notify_verdict(job_id: str, phone: str, verdict_line: str) -> None:
    send(phone, f"Reality Check verdict: {verdict_line} Details: {PUBLIC_BASE}/verdict/{job_id}", job_id=job_id)


def register() -> None:
    from reality_check import panels
    panels.register(LinqPanel())
