"""Buyer agent: an autonomous landing-page writer that buys judgment when it should.

This is the before/after demo. The agent writes copy, asks Reality Check whether a stranger can
tell what the company does, and only when the router says humans are worth buying does money
move. If humans say no, the agent rewrites using their words and checks again.

Usage:
  .venv/bin/python demo/buyer_agent.py "PitchPolish, an AI that rewrites YC applications" \
      --base http://localhost:8000 --stakes 100 --budget 8 --paid 8 --wait 900

Requires GROQ_API_KEY (or OPENAI_API_KEY as fallback) for the writer model.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import httpx

WRITER_BASE = os.environ.get("RC_WRITER_BASE", "https://api.groq.com/openai/v1")
WRITER_MODEL = os.environ.get("RC_WRITER_MODEL", "llama-3.3-70b-versatile")


def _writer_key() -> tuple[str, str, str]:
    if os.environ.get("GROQ_API_KEY"):
        return os.environ["GROQ_API_KEY"], WRITER_BASE, WRITER_MODEL
    if os.environ.get("OPENAI_API_KEY"):
        return os.environ["OPENAI_API_KEY"], "https://api.openai.com/v1", "gpt-4o-mini"
    sys.exit("need GROQ_API_KEY or OPENAI_API_KEY for the writer")


def write(product: str, feedback: list[str] | None = None) -> str:
    key, base, model = _writer_key()
    sys_prompt = ("You write landing-page hero copy: a headline and two sentences. Plain words. "
                  "Say what it is, who it is for, what it costs. No hype, no jargon.")
    user = f"Product: {product}"
    if feedback:
        user += "\n\nReal people read the last version and said:\n- " + "\n- ".join(feedback) + \
                "\n\nRewrite so those people would understand it on first read."
    r = httpx.post(f"{base}/chat/completions", timeout=60, headers={"Authorization": f"Bearer {key}"},
                   json={"model": model, "messages": [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user}],
                         "temperature": 0.7, "max_tokens": 300})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


DEV = os.environ.get("RC_DEV") == "1"


def judge(base: str, copy: str, stakes: float, budget: float, paid: float, wait_pay_s: int = 600) -> dict:
    """Paid path: create an order, hand the Payment Link to whoever pays (QR at the table or the
    agent's own card), and wait for the Stripe poller to start the job. Dev path (RC_DEV=1 on both
    sides): the X-RC-Paid header, revenue not Stripe-backed and labeled as such."""
    body = {"input": copy, "sku": "reality_check", "evidence_standard": "voi_routed", "cost_if_wrong_usd": stakes,
            "max_budget_usd": budget, "buyer_id": "agent:landing-writer"}
    if not paid or DEV:
        r = httpx.post(f"{base}/judge", timeout=180, headers={"X-RC-Paid": str(paid)} if (paid and DEV) else {}, json=body)
        r.raise_for_status()
        return r.json()
    o = httpx.post(f"{base}/order", timeout=60, json=body).raise_for_status().json()
    print(f"  order {o['job_id']}: pay ${o['price_usd']:.2f} at {o['pay_url']}", flush=True)
    t0 = time.time()
    while time.time() - t0 < wait_pay_s:
        v = httpx.get(f"{base}/order/{o['job_id']}", timeout=180).json()
        if v.get("status") != "pending_payment":
            return v
        time.sleep(5)
    raise SystemExit("payment did not arrive; nothing judged, nothing spent")


def wait_for_humans(base: str, job_id: str, timeout_s: int) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        v = httpx.get(f"{base}/judge/{job_id}", timeout=30).json()
        if v["status"] == "settled":
            return v
        print(f"  waiting for humans... {v['n_humans']} answered  (rate page: {base}/rate/{job_id})", flush=True)
        time.sleep(10)
    return httpx.get(f"{base}/judge/{job_id}", timeout=30).json()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("product")
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--stakes", type=float, default=100.0)
    ap.add_argument("--budget", type=float, default=8.0)
    ap.add_argument("--paid", type=float, default=8.0, help="what the agent pays per check (0 = unpaid dev call)")
    ap.add_argument("--wait", type=int, default=900)
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--dry-stakes", type=float, default=20.0,
                    help="first, one call at low stakes to show the router REFUSING to buy humans")
    a = ap.parse_args()

    if a.dry_stakes > 0:
        v0 = judge(a.base, write(a.product), a.dry_stakes, a.budget, 0.0)
        voi0 = v0.get("voi") or {}
        print(f"[low stakes ${a.dry_stakes:.0f}] router: {voi0.get('reason')}  buy={voi0.get('buy')}")

    log: list[dict] = []
    feedback: list[str] = []
    copy = write(a.product)
    for rnd in range(1, a.rounds + 1):
        print(f"\n=== round {rnd} ===\n{copy}\n")
        v = judge(a.base, copy, a.stakes, a.budget, a.paid)
        voi = v.get("voi") or {}
        print(f"router: {voi.get('reason')}  (net value ${voi.get('net_value_usd', 0):.2f})")
        if v["status"] == "awaiting_humans":
            v = wait_for_humans(a.base, v["job_id"], a.wait)
        print(f"verdict: {v['verdict']} p={v['p']} agreement={v['agreement']} humans={v['n_humans']}  {v['summary']}")
        log.append({"round": rnd, "copy": copy, "verdict": v})
        if rnd == 1 and v["status"] == "settled":
            httpx.post(f"{a.base}/before_after/lock/{v['job_id']}", timeout=30)  # pre-register the "before"
        if v["verdict"] == "yes":
            print("\nagent: strangers understand it. shipping.")
            break
        feedback = [h["text"] for h in v.get("human_answers", []) if h.get("text")] or [v.get("minority_view", "")]
        print("agent: rewriting from human feedback:", feedback)
        copy = write(a.product, feedback)
    print("\n=== before/after ===")
    if len(log) >= 2:
        cmp_ = httpx.get(f"{a.base}/before_after/{log[0]['verdict']['job_id']}/{log[-1]['verdict']['job_id']}", timeout=30).json()
        print("pre-registered comparison:", cmp_.get("decision"), cmp_.get("verdict"))
    for e in log:
        vv = e["verdict"]
        print(f"round {e['round']}: verdict={vv['verdict']} p={vv['p']} humans={vv['n_humans']} revenue=${vv['revenue_usd']:.2f} cost=${vv['evidence_cost_usd']:.2f}")
    with open("demo/last_run.json", "w") as f:
        json.dump(log, f, indent=1)


if __name__ == "__main__":
    main()
