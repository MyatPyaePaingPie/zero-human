---
type: research
created: 2026-08-15
status: complete, go/no-go below
topic: zero-human-company-hackathon
---
# Zero Human Company Hackathon: research memo + go/no-go (money-swarm-first)

Companion: the augur chat writes `_meta/reports/zero-human-hackathon-memo.md` (augur-first). This
file owns money swarm reuse and the synthesis; do not duplicate augur depth here.

Build window: 10:45 to 18:45 today (8h). Judging 19:00. Two $2,500 prizes worth aiming at:
Best Overall Project and Best Overall Agent-Run Company (real Stripe-visible revenue).

## 0. Answers in one line each

- Stripe: LIVE account already activated (Design ELF, `charges_enabled` + `payouts_enabled` true, checked via `stripe get /v1/account --live`). Payment collection is unblocked; the only remaining step is the payment link + restricted read-only key.
- Money swarm: reuse the ring policy engine (spend authority as code), the Thompson bandit (evidence-provider allocation), the experiment decision/critic hash-binding (before/after study), and the external-agent protocol (buyer requests are information, never authority). All stdlib, all small.
- Money swarm's own demand-to-build gate says: a net-new build needs a payer and a paid test, concierge-first. That is the tiebreaker for the go/no-go below.
- Augur: consensus dissent-trigger (`core/consensus.py`) + provider cost/quality routing are nearly free; a real value-of-information gate is NOT in augur and would be new math. VOI = narrative, dissent = mechanism.
- External agent payment today: YES via x402 (USDC on Base, CDP Bazaar discovery, OpenClaw wallet skills exist). Stripe Machine Payments accepts x402-on-Base and lands it in the Stripe balance IF enabled (US ex-NY, else email Stripe). So machine revenue CAN be Stripe-visible, but do not bet the demo on the enablement.
- Terac MCP: real, 7 tools at `https://terac.com/api/mcp` + REST v2. Docs' own example: $28 per expert, ETA 6h, delivered 5h12m. Panel is verified experts, not crowd. A cheap fast general-population tier is implied by the guide ("launch General Population studies for fastest results") but NOT found in docs. Single highest-leverage question at the 10:20 sponsor Q&A.
- Competitors: MeatSpace (meatspace.run) and HumanRail are our pitch verbatim; SanctifAI is the funded incumbent. Nobody sells "was this question worth $X of human time" (VOI routing). That is the only unoccupied seat, and it is exactly what makes slow expensive Terac defensible.
- Verdict: GO, reshaped. Sell the routing decision. Launch the Terac study by 11:30 or it will not return before judging.

## 1. Money swarm findings (primary dig)

Repo: `money-swarm/` (Vaults root). ~2,900 commits on the shared Vaults history; the swarm itself
is a stdlib-only Python spine with append-only JSONL as truth and SQLite as a disposable view.

What it is: a revenue *opportunity* OS. It scores lanes, defines bounded paid experiments,
classifies every external action into rings, and refuses to send/spend without a hash-bound
approval. It has executed exactly one Ring 0 action ever (a skill publish, 2026-07-19). It has
never taken money and never spent money. So it is a governance spine, not a revenue engine.

Directly reusable for the judgment company:

| Piece | File | Why it matters here | Lift cost |
|---|---|---|---|
| Ring policy engine | `money-swarm/automation/policy.py` (229 lines) | "Code decides authority; language never does." Fail-closed classify(): unknown kind = Ring 2; free text can never raise a ring; `may_execute()` only on Ring 0 or hash-bound approval. This IS the "human pre-authorizes a budget, agent spends inside it, nothing else" shape. Rename rings to spend tiers: Ring 0 = inside pre-signed judgment budget, Ring 2 = anything else. | ~30 min: fork, swap RING0_KINDS for `buy-judgment` with a budget cap check |
| Policy envelope | `policy.py::_live_envelope`, `state/policy-envelope.json` (absent by design) | Signed-once, expiring, revocable spending envelope. Exactly the "human authorizes $20/day" mechanism the handoff wants. Today it fails closed because no envelope exists; we write one. | ~15 min |
| Thompson bandit | `money-swarm/automation/lineage/bandit.py` (103 lines, stdlib) | Beta-Bernoulli allocation over named arms. Arms = evidence strategies (model-consensus / 1 human / 5 humans / expert). Reward = did the verdict hold up (buyer accepted, or second study confirmed). Gives "seller decides how much evidence to buy" a learning mechanism in 100 lines. | ~20 min |
| Lineage event log | `lineage/lineage.py` | Posteriors rebuilt from JSONL, receipts required per outcome ("no receipt, no outcome"). Use as the evidence-strategy ledger. | ~20 min |
| Experiment decision + critic | `automation/experiments.py` | Pre-registered pass/fail/kill, `validity_checked`, guardrails, critic receipt bound to sha256 of the decision payload. Directly the before/after study record Terac judges want, and it forbids "looks like a win" (failure mode #15). | ~20 min |
| External-agent protocol | `automation/agent_protocol/protocol.py` (405 lines) | Inbound agent messages: quarantine body_text, content_sha256, nonce replay guard, expiry, risk flags, authority claims discarded. This is the front door for a *buyer agent* hitting our endpoint: its request is information; it can never talk its way into free judgment or into changing our spend. | ~30 min to wrap as the request parser |
| Outcomes ledger | `metrics/outcomes.jsonl` + `validate.py` BASE_FIELDS | Revenue / cost / margin receipts with expected_value, kill_date. Use verbatim for the dashboard's numbers. | ~10 min |
| Failure-mode table | `_meta/research/money-swarm-failure-modes.md` | #1 idempotency key before side effect (Stripe webhook double-fires WILL happen), #6 approval bound to payload hash, #14 dedupe revenue events by stable id, #15 pre-registered study rules. Read once, avoids four known bites. | read only |

What money swarm does NOT give us: any payment rail, any buyer, any external agent that has ever
paid, any latency data. Its `demand-to-build.md` gate (payer, painful job, current spend, reachable
audience, paid test in <=7 days, kill rule, `paid_test_cleared: true`) is the honest yardstick:
"judgment for agents" has zero of seven evidenced. The room of ~200 humans is the reachable
audience; the paid test is today.

Doctrinal reuse (cheap, high judge-signal): money swarm's line "code decides authority; language
never does" is a great answer to "how do you know the agent won't overspend": the LLM never holds
the budget, `policy.py` does.

## 2. Augur findings (synthesis; the augur chat owns depth)

Repo: `CodingVault/augur`. Verdict from a read-only recon of core/, runtime/, wide_edge/, reports:

Nearly free (stdlib, copy-paste, tests exist):
- Consensus with dissent: `augur/core/consensus.py::evaluate()` takes N staked `Forecast(p, confidence, refuted_by)` votes and returns majority + `dissent_score`, with a threshold branch already written (currently "low dissent -> skip"). Invert one branch and "high dissent -> buy human judgment" is the mechanism. Gotcha: :88-116 collapse ties and low-dissent into one `skip`; the polarity is opposite to ours, read before reuse.
- Provider routing by measured cost/quality: `ProviderResult(cost_usd_estimate, latency_ms)`, per-provider Beta posteriors (`runtime/resolve.py::_update_provider_posteriors`), and `tools/provider_bakeoff_report.py::edge_per_dollar`. That is the evidence-broker scoring function, already measured on real runs.
- `core/brier.py`, `core/bandit.py` (Thompson/UCB/eps-greedy + allocate), `core/lifecycle.py` (confidence update on support/refute), `wide_edge/models.py` (`LedgerEntry spend|deploy|return`, `Settlement` with burn and net_edge: a ready cost-of-judgment vs value-of-judgment ledger).

NOT free: a real value-of-information gate. Nothing in augur computes E[loss|no info] minus E[loss|info]; `kelly.size_position` is a sizing-under-calibration gate, not an information-purchase gate. Reusing it would be the shape without the math. Real VOI needs a loss function over the buyer's downstream decision, which augur never had. Recommendation: VOI is the narrative, dissent-triggered escalation is the mechanism.

Prior art inside augur for "agent decides to spend": AgentPay in `_meta/commissions/active/2026-06-29-wide-edge-pilot.md:201-226`, a spend-permission policy layer, testnet only, deliberately never made live, "human-gated freeze, fail-closed". `lifecycle.py:12-13` has human-approval-gated transitions marked out of scope. Both are the same lesson money swarm learned: code holds the budget.

Gotchas that would bite today: correlated re-logs inflated n by ~165x and lit a false "cleared" badge (dedupe evaluator votes per item, one shared predicate); own-calibration is not edge (any "should I buy judgment" score must be relative to the free baseline, i.e. model-only verdict); fail closed when unmeasured; never let simulated judgment cost be free-by-construction; `fitness_bridge` silently stubs zeros.

Overlap with money swarm: both have a Thompson bandit (money-swarm's is 103 lines and cleaner; augur's has `allocate()` with floors and kill). Pick money-swarm's bandit + augur's consensus + augur's `Settlement` ledger. Skip augur's kelly, tick, dashboard, venues.

## 3. External research: agent payment, Terac, competitors

Full file with URLs and confidence labels: `_meta/research/zero-human-hackathon-external-2026-08-15.md`.
Three facts that reshape the plan:

1. Terac economics. Feasibility quote flow: `terac_request_feasibility {role, task, count}` -> quote (`cpi_usd`, eta) -> `terac_launch_draft_opportunity` -> submissions -> approve (billed only on approved). Documented example is $28/response and ~6h. Webhooks documented, but `listSubmissions` polling is fine for today. Consequence: one Terac study, launched in hour one, n small, is the before/after. Not "buy 5 humans per API call at $0.50".
2. External agents can pay today via x402. CDP Bazaar lists x402 endpoints for agent discovery; ClawHub has wallet + x402 skills. Stripe Machine Payments would make that x402 USDC land in the Stripe balance (visible to the organizers' restricted key) if the account is enabled. Check enablement in the Stripe dashboard in the first 15 minutes; if blocked, x402 revenue is real but organizer-invisible, and Stripe payment links from human buyers are the counted revenue.
3. The lane is crowded: MeatSpace, HumanRail, SanctifAI, AskHuman. Plain "human judgment API" is dead on arrival for the creativity prize. The unoccupied seat is the routing layer: "is more information worth buying before this agent acts?" Frame everything around that.

## 4. Stripe revenue path

Verified now: `stripe get /v1/account --live` on the default profile returns
`charges_enabled: true, payouts_enabled: true, details_submitted: true` (Design ELF, company).
Live balance $0. Second profile `acct_1TjWiHABBfea7yRc` exists, unexplored.

Path (15 min): Payment Link with "customer chooses price" (or fixed tiers) via CLI or dashboard;
restricted key with Balance:read + Charges:read only; submit to organizers. Webhook or polling on
`checkout.session.completed` triggers fulfillment; idempotency key = session id (failure mode #1).

Machine payments (x402/USDC) do NOT land in Stripe charges. If an external agent pays in USDC it
is invisible to the organizers' revenue check unless (a) we ask them to accept a second rail, or
(b) the agent pays via Stripe (card token / Agent Toolkit). Treat Stripe as the ONLY revenue path
that counts today; anything else is demo garnish.

## 5. Kill criteria (hard windows)

- 11:30: if no verified way for a genuinely external agent to pay a $1 call that lands in Stripe, buyer-agent = our own agent under a signed envelope, and the humans in the room become the paying customers. No more time on payment infra after this.
- 12:15: Terac study created + first result retrieved via MCP, or Terac is used only for one visible before/after and the fallback flow proceeds.
- 14:30: full round trip (pay -> judgment -> verdict -> behavior change) works once end to end, or cut scope to the concierge version.
- 17:30: freeze; dashboard + demo script only.

## 6. Go/no-go and recommended shape

GO on the judgment company, with three reshapes forced by the evidence:

- The product is the routing decision, not the survey. Name it around "an autonomous company should know when not to trust itself." Mechanism (all lifted): N model evaluators vote (`augur/core/consensus.py`, dissent_score), a spend envelope in code (`money-swarm/automation/policy.py`), a Thompson bandit over evidence arms (`money-swarm/automation/lineage/bandit.py`), a `Settlement`-style ledger for cost vs value (`augur/wide_edge/models.py`). VOI is stated as expected-loss arithmetic in the dashboard but computed from dissent + stakes; say so honestly.
- Two revenue rails, one counted. Stripe payment link (humans in the room, "customer chooses price") is the counted revenue. An x402-priced endpoint of the same service, listed on Bazaar, is the machine rail; it counts only if Stripe Machine Payments is enabled on the account. Either way the seller-side decisions (how much evidence to buy, when to hire Terac) are autonomous and identical.
- Terac is used once, early, and visibly. Launch a small general-population study by 11:30 on a real artifact (a buyer's landing page or one of ours): "what does this company do?" Its return is the before/after; a second, smaller confirmation study only if the first returns before 15:00. Every other "human judgment" during the day comes from the fast arms (model consensus, historical priors, humans physically in the room via Linq tapback vote if we take that lane).

Minimum demo (8h, in build order):
1. 10:45-11:15 Stripe: payment link, restricted key, check Machine Payments enablement. Terac: OAuth the MCP, request feasibility, get the real quote and ETA. Both are receipts for the memo, not code.
2. 11:15-11:30 Launch the Terac study on the demo artifact. Clock starts.
3. 11:30-13:30 The router: `judge(input, question, stakes, budget)` -> evaluators -> dissent -> envelope check -> arm choice -> verdict, all logged to JSONL. Money-swarm protocol.py wraps inbound requests. Local first, then one endpoint (Render or a Worker).
4. 13:30-15:00 Buyer agent: our own agent, signed envelope of $20, building a landing page, hits the router at the "does this read clearly" step. x402 wrapper on the endpoint if Stripe Machine Payments is on; skip if not.
5. 15:00-16:30 Terac results in -> settlement -> buyer rewrites -> before/after shown. First human sales in the room via QR to the Stripe link ("5 real judgments on your page, delivered by text").
6. 16:30-17:30 Dashboard = the decision log (request, dissent, EV reasoning, price, arm, Terac spend, verdict, buyer change, revenue, cost, margin). No decorative charts.
7. 17:30 freeze.

Fallback (decide at 14:30 kill point): same router, human buyer only. "Five real people tell you what your landing page says, plus the fixes." Stripe link, Terac or in-room panel fulfilment, verdict by Linq text. Less novel, still real revenue, still a clean Terac before/after.

Anti-goals confirmed by this research: no generic marketplace, no second prediction market, no crypto rail work past the 11:30 kill window, no seven-sponsor bingo. Sponsors that are structurally load-bearing: Terac, Stripe, maybe Linq (delivery + tapback as in-room fast judgment arm), maybe Render (host). Everything else is off unless free.

## 7. Open questions for the room (ask at 10:20 sponsor Q&A)
1. Terac: is there a general-population tier with small n at low cost and sub-hour turnaround? What is the hackathon credit balance?
2. Organizers: does x402/USDC revenue count if it settles into the Stripe balance via Machine Payments? Is the restricted key on balance+charges enough to see it?
3. Stripe booth: can they flip Machine Payments on for the Design ELF account today?
