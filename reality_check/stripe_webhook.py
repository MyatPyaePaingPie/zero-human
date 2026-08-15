"""Stripe: the only path by which a job becomes PAID.

Flow (Payment Link + client_reference_id, no Checkout Session API needed):
  POST /order {JudgeRequest}          -> creates job in status pending_payment, returns pay_url
                                          = RC_PAYLINK_<SKU> + ?client_reference_id=<job_id>
  Stripe -> POST /stripe/webhook       checkout.session.completed with client_reference_id
                                       -> idempotent on session id -> ledger revenue -> judge.start
  GET /order/{job_id}                  -> verdict or pending_payment

Signature verification is stdlib HMAC per Stripe's scheme (t=..., v1=...), secret in
STRIPE_WEBHOOK_SECRET. Idempotency key = the checkout session id (money-swarm failure mode #1:
webhooks double-fire; claim the key before any side effect). Amount comes from the event, never
from the request body (protocol rule: paid status is a receipt, not a claim).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from reality_check import judge, skus, store
from reality_check.core.models import JudgeRequest
from reality_check.policy import protocol

router = APIRouter()
TOLERANCE_S = 300


def pay_link(sku: str) -> str | None:
    return os.environ.get(f"RC_PAYLINK_{sku.upper()}") or os.environ.get("RC_PAYLINK_DEFAULT")


def verify_signature(payload: bytes, sig_header: str, secret: str, now: float | None = None) -> bool:
    try:
        parts = dict(kv.split("=", 1) for kv in sig_header.split(","))
        ts = int(parts["t"])
        v1s = [v for k, v in (kv.split("=", 1) for kv in sig_header.split(",")) if k == "v1"]
    except (ValueError, KeyError):
        return False
    if abs((now or time.time()) - ts) > TOLERANCE_S:
        return False
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, v) for v in v1s)


def _claimed(session_id: str) -> bool:
    """Idempotency: True if this session id was already processed."""
    with store.conn() as c:
        row = c.execute("SELECT 1 FROM events WHERE kind='stripe.session' AND payload=? LIMIT 1",
                        (json.dumps({"session": session_id}),)).fetchone()
        if row:
            return True
        c.execute("INSERT INTO events(job_id,kind,payload,created_at) VALUES(NULL,'stripe.session',?,?)",
                  (json.dumps({"session": session_id}), store.now()))
    return False


def complete_session(session: dict) -> dict:
    """Turn one paid Checkout Session into revenue + a started job. Idempotent on session id.
    Shared by the webhook and the read-only poller (stripe_poll.py); the amount always comes
    from Stripe, never from a request body."""
    session_id = session["id"]
    if (session.get("payment_status") or "paid") != "paid":
        return {"unpaid": session_id}
    if _claimed(session_id):
        return {"duplicate": session_id}
    amount = float(session.get("amount_total") or 0) / 100.0
    job_id = session.get("client_reference_id")
    email = (session.get("customer_details") or {}).get("email")
    store.event(job_id, "stripe.paid", {"session": session_id, "amount_usd": amount, "email": email})
    job = store.get_job(job_id) if job_id else None
    if job and job["status"] == "pending_payment":
        req = JudgeRequest(**job["request"])
        judge.start(req, paid_usd=amount, job_id=job_id)  # ledger revenue row is written inside start()
        return {"started": job_id, "amount_usd": amount}
    if not job:
        # paid with no matching order (QR walk-up): placeholder job the operator fills in
        jid = job_id or f"walkup-{session_id[-8:]}"
        store.put_job(jid, email or "walkup", "pending_payment",
                      {"sku": "reality_check", "input": "", "claims": skus.default_claims("reality_check")}, {"walkup": True})
        store.ledger_add(jid, "revenue", amount, f"stripe {session_id} (walk-up, awaiting input)")
        return {"walkup": jid, "amount_usd": amount}
    return {"noop": job_id, "status": job["status"]}


@router.post("/order")
async def create_order(request: Request):
    body = await request.json()
    adm = protocol.admit(body, headers=dict(request.headers))
    if not adm.admitted:
        raise HTTPException(409, adm.reason)
    try:
        req = JudgeRequest(**body)
    except Exception as exc:
        raise HTTPException(422, str(exc))
    job_id = uuid.uuid4().hex[:12]
    store.put_job(job_id, req.buyer_id, "pending_payment", req.model_dump(), {"content_sha256": adm.content_sha256})
    protocol.record(job_id, adm)
    link = pay_link(req.sku)
    pay_url = f"{link}?client_reference_id={job_id}" if link else None
    store.event(job_id, "order.created", {"sku": req.sku, "price_usd": skus.price(req.sku), "pay_url": pay_url})
    return {"job_id": job_id, "status": "pending_payment", "price_usd": skus.price(req.sku), "pay_url": pay_url,
            "authority_claims_discarded": adm.authority_claims_discarded}


@router.get("/order/{job_id}")
def get_order(job_id: str):
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    if job["status"] == "pending_payment":
        return {"job_id": job_id, "status": "pending_payment", "pay_url": (f"{pay_link(job['request']['sku'])}?client_reference_id={job_id}" if pay_link(job["request"]["sku"]) else None)}
    return judge.verdict(job_id).model_dump()


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    sig = request.headers.get("stripe-signature", "")
    if not secret or not verify_signature(payload, sig, secret):
        raise HTTPException(400, "bad signature")
    event = json.loads(payload)
    if event.get("type") != "checkout.session.completed":
        return JSONResponse({"ignored": event.get("type")})
    return JSONResponse(complete_session(event["data"]["object"]))
