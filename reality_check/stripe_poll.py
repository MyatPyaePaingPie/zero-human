"""Stripe read-only poller: revenue truth without a public webhook endpoint.

Every STRIPE_POLL_S seconds (default 15) list recent Checkout Sessions with the restricted
READ-ONLY key in ZEROHUMAN_STRIPE_RESTRICTED_KEY (the same class of key the organizers get: Checkout Sessions
read + Charges read + Balance read). Paid sessions are handed to stripe_webhook.complete_session,
which is idempotent on session id, so the poller and the webhook can both run.

Why a poller: no secret key on the box, no dashboard webhook setup, no tunnel needed, and our
ledger matches what the organizers see on the account by construction. Payment Link buyers carry
?client_reference_id=<job_id>; walk-ups without one become placeholder jobs.

Env: ZEROHUMAN_STRIPE_RESTRICTED_KEY (required to run; absent = poller never starts, event stripe.poll.off),
STRIPE_POLL_S, STRIPE_POLL_LIMIT.
"""
from __future__ import annotations

import os
import threading
import time

import httpx

from reality_check import store
from reality_check.stripe_webhook import complete_session

API = "https://api.stripe.com/v1/checkout/sessions"
_thread: threading.Thread | None = None


def fetch_paid_sessions(key: str, limit: int = 25) -> list[dict]:
    r = httpx.get(API, params={"limit": limit}, auth=(key, ""), timeout=15.0)
    r.raise_for_status()
    return [s for s in r.json().get("data", []) if s.get("payment_status") == "paid"]


def poll_once(key: str, limit: int = 25) -> list[dict]:
    out = []
    for s in fetch_paid_sessions(key, limit):
        res = complete_session(s)
        if "duplicate" not in res:
            out.append(res)
    return out


def _loop(key: str, every: float, limit: int) -> None:
    while True:
        try:
            for res in poll_once(key, limit):
                store.event(None, "stripe.poll", res)
        except Exception as exc:  # network blips must not kill the thread
            store.event(None, "stripe.poll.error", {"error": str(exc)[:300]})
        time.sleep(every)


def start_background() -> bool:
    global _thread
    key = os.environ.get("ZEROHUMAN_STRIPE_RESTRICTED_KEY") or os.environ.get("ZEROHUMAN_STRIPE_WRITE_KEY", "")
    if not key:
        store.event(None, "stripe.poll.off", {"reason": "no ZEROHUMAN_STRIPE_RESTRICTED_KEY / ZEROHUMAN_STRIPE_WRITE_KEY"})
        return False
    if _thread and _thread.is_alive():
        return True
    every = float(os.environ.get("STRIPE_POLL_S", "15"))
    limit = int(os.environ.get("STRIPE_POLL_LIMIT", "25"))
    _thread = threading.Thread(target=_loop, args=(key, every, limit), daemon=True, name="stripe-poll")
    _thread.start()
    store.event(None, "stripe.poll.on", {"every_s": every, "limit": limit})
    return True
