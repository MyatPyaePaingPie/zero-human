# Policy, protocol, learning: what money swarm and augur add to Reality Check

The router (`judge.py`) decides whether to buy judgment. These modules decide whether the
company MAY spend, whether a buyer's words count for anything, and whether any of it worked.
All are stdlib on top of `store.py`; every number is rebuilt from the ledger and event log on
each call, never held in memory. Provenance: money-swarm `automation/policy.py`,
`agent_protocol/protocol.py`, `experiments.py`, `lineage/`; augur `core/brier.py`,
`core/consensus.py`, real-money readiness report 2026-06-12.

## 1. Spend envelope `reality_check/policy/envelope.py`

Code decides authority; language never does. The buyer's `max_budget_usd` is a request; the
signed envelope in `state/envelope.json` is the company's answer. Before any human panel launches:

| check | fail-closed behaviour |
|---|---|
| envelope missing / unreadable / expired / unsigned / bad HMAC | only free arms (`ensemble`, `local`) may run |
| arm not in `allowed_arms` | deny |
| price > `per_job_cap_usd` | deny |
| today's `cost.*` ledger + price > `daily_cap_usd` | deny |
| price > paid × (1 − `min_margin_ratio`) | deny (never sell at a loss) |

Signing: copy `state/envelope.example.json` to `state/envelope.json`, export `RC_ENVELOPE_SECRET`,
run `python -m reality_check.policy.envelope sign`. `python -m reality_check.policy.envelope`
prints live/spent. The LLM never sees the envelope; free text in a request cannot raise a cap.

Wiring (one block in `judge.start`, before `panel.launch`):
```python
from reality_check.policy import envelope
price = voi_arm_price(decision.arm)   # the arm's price_usd from the arms tuple
if decision.buy and not envelope.gate_panel_launch(job_id, decision.arm, price, paid_usd):
    decision = decision.model_copy(update={"buy": False, "reason": "envelope denied: " + decision.reason})
```
`gate_panel_launch` writes an `envelope.checked` event with the reason and never raises.

## 2. Inbound protocol `reality_check/policy/protocol.py`

Information crosses, authority never. `protocol.admit(body, headers, job_id)` hashes the request,
rejects nonce replays (`X-RC-Nonce`) and expired messages (`X-RC-Expires`), and lists any
authority claims found in free text ("already paid", "force humans", "no budget limit", "ignore
previous instructions", "skip the gate") as `authority_claims_discarded`. They grant nothing.
`paid_usd` comes only from ledger `revenue` rows for the job (Stripe webhook / x402 receipt), or
from `X-RC-Paid` when `RC_DEV=1`. This replaces the header hole in `/judge`.

## 3. Learning from receipts `reality_check/policy/learning.py`

Every settled job with humans is scored against the human majority (augur brier pattern):

- **Arm gain**: per evidence arm, `n_settled`, `overturned_jobs`, `measured_gain` = share of
  internal error removed (fraction of ensemble brier on jobs where humans overturned the models,
  relative to the ensemble baseline). Below `voi.MIN_SETTLED` (10) the VOI gate keeps the prior
  and says so. `learning.arms()` returns `voi.DEFAULT_ARMS` with measurements attached; pass it as
  `voi.decide(..., arms=learning.arms())`. One job counts once (augur ~165x re-log lesson).
- **Evaluator reputation**: mean brier vs humans and overturned share per persona id.
- **Swarm check**: does collaboration help? Per settled job, ensemble brier vs best / median /
  worst single evaluator, cumulative deltas (`> 0` = swarm helped), cost of the ensemble vs one
  evaluator, and a plain verdict: "swarm beat even the best lone agent", "beat a typical lone
  agent, not the best", or "did NOT beat a lone agent; it added cost and latency". Unmeasured
  under 3 jobs. This is the coordination-null test from augur wide_edge as a dashboard number.

`learning.report()` returns all three for `GET /learning` and the dashboard. Never raises.

## 4. Pre-registered before/after `reality_check/before_after.py`

`lock(before_job_id)` stores the hash of the before verdict; `compare(before, after)` returns
per-claim deltas, overall `delta_p`, evidence cost, revenue, and a critic receipt bound to the
hash of the comparison. It is `invalid` (not pass/fail) when: no lock, the before verdict changed
after the lock, the lock happened after the after-job's humans started answering, the after job
has no humans, or the inputs are identical. Money-swarm failure mode #15: pre-register or it is
not a result. Suggested endpoints: `POST /before_after/lock/{job}`, `GET /before_after/{b}/{a}`.

## 5. Terac panel `reality_check/terac_client.py`

`TeracPanel` implements the `panels.Panel` contract over REST v2: creates an opportunity with one
`activity` task (`review_type=auto_approve`, `task_url=/rate/{job}?src=terac`,
`unrestricted_audience=true`), launches it, records `terac.launched` with the API's pricing, and
returns a handle whose `price_usd` goes to the ledger as `cost.terac`. No key → dry handle,
`terac.dry` event, $0. API error → `terac.error`, nothing charged. `register()` adds it to the
panels registry. Answers arrive on our `/rate` page; Terac appends `teracSubmissionId`.

## 6. Stripe `reality_check/stripe_webhook.py`

`POST /order` admits the request through the protocol, creates a `pending_payment` job, returns
`pay_url` = `RC_PAYLINK_<SKU>?client_reference_id=<job_id>`. `POST /stripe/webhook` verifies the
Stripe signature (stdlib HMAC, 300s tolerance), claims the checkout session id before any side
effect (webhooks double-fire), writes `stripe.paid`, and calls `judge.start(req, paid_usd=amount,
job_id=job_id)`. Walk-up payments with no order become a placeholder job holding the revenue.
Amounts come only from the Stripe event.

## Tests

`tests/test_policy.py`: envelope fail-closed and caps, signature rejection, protocol authority
discard + replay, learning report and arm attachment, before/after lock semantics, Stripe
signature + idempotency. `pytest -q` → 12 passed with `tests/test_loop.py`.

## What this buys on stage

"How do you know the agent won't overspend?" The LLM never holds the budget, `envelope.py`
does. "Did the humans actually help?" `learning.arms()` shows measured gain and n. "Does
collaboration help or just add latency?" `swarm_check` says which, with the number. "Prove the
before/after." A locked hash and a critic receipt, or `invalid`.
