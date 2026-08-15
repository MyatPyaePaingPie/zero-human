---
type: report
status: active
created: 2026-08-15
---

# Zero Human Company hackathon: research memo + go/no-go

Written 2026-08-15 morning, before the 10:45 hacking start. Eight-hour window (10:45 to 18:45).
Lane findings with URLs: `_meta/research/zero-human-hackathon/{augur,terac,payment,sponsor}-findings.md`.
Everything marked UNVERIFIED there stays unverified here.

## Decision in one paragraph

GO on the judgment company, NO-GO on betting the demo on a genuinely external agent buyer.
Build "Reality Check": a service that decides *whether uncertainty is worth paying to reduce*, buys the
cheapest sufficient evidence (model ensemble, in-room humans over Linq, Terac general population, Terac
expert), and returns a structured verdict. Revenue comes from two lanes at once: a Stripe Payment Link
sold to humans in the room (guaranteed, judge-visible) and a machine-payment lane where a policy-capped
agent wallet WE fund pays our x402 endpoint whose payTo is a Stripe crypto deposit address (machine-
originated, judge-visible, honestly labelled "our wallet, not external"). Terac is the settlement oracle
and the before/after requirement is satisfied by the same loop. Two things can kill it and both are
checkable before noon: Terac's real fill latency during the event, and Stripe's crypto payment-method
review.

## 1. Augur findings (deep read, details in augur-findings.md)

Augur has zero value-of-information machinery and no human oracle. What it has is a skepticism toolkit
that maps almost 1:1 onto the judgment problem:

- `augur/core/consensus.py`: N evaluators emit `Forecast(p, confidence, side)`; `evaluate()` returns
  verdict, agreed_p, voters for/against, `dissent_score`, and downgrades to `skip` when dissent is high.
  "Disagreement means uncertainty" is already the doctrine. `skip` becomes "buy external judgment".
- `augur/core/bandit.py` (222 lines, stdlib only): Thompson/UCB1 arms with Beta posteriors,
  `allocate()`, `update_posterior(arm, beat_crowd)`. Arm = evaluator or evidence source; reward = loss
  reduction per dollar. This is the evidence router.
- `augur/core/brier.py` + `augur/wide_edge/scoring.py`: settlement scoring, calibration deciles,
  block-bootstrap CI, n>=30 clearance gate. This scores evaluators against the human oracle.
- `augur/core/kelly.py` gate shape (fail closed, confidence floor, edge floor, capped fraction). Formulas
  are binary-market specific; lift the shape, write `should_buy_judgment` fresh (~30 lines):
  `buy iff E[loss | no purchase] - E[loss | purchase] > price + margin`.
- `augur/wide_edge/`: the 2026-06-29 "autonomous company loop" commission. Role-tagged decision log,
  AgentPay-vocabulary paper ledger, pre-registered contracts, forward-leakage guard. Only ran on
  synthetic fixtures; stalled 2026-06-30 waiting on Apify/crystal-os/AgentPay. It is the closest prior
  art and its `DecisionLogEntry`/`LedgerEntry` dataclasses are the dashboard's data model.

Verdict on the three questions: (a) VOI-as-purchase-rule is elegant with augur's parts, but the VOI
expression itself must be written today; (b) evaluator market -> disagreement -> buy human -> human
settles -> reputation reweights is ~150 lines using bandit + consensus + brier, so not overcomplication
IF we vendor functions rather than import augur's runtime/DB; (c) augur is a parts bin plus a list of
traps, not a spine. Lift five modules (~600 lines, ~2 hours including wiring); import nothing else.

Traps that transfer directly: dedupe by decision_id (augur inflated n 165x), any "our judgment helped"
claim must be relative to the buyer's free prior (own-Brier gates cleared a losing model), LLM
self-confidence was anti-predictive so it never prices a purchase alone, budget constants that flip
the sign are free parameters, seed every draw and report expected allocation, direction-aware gates,
never leak the human answer into evaluators before they commit.

## 2. Reusable now (ranked, minutes)

1. `bandit.py` verbatim + `_expected_allocation` from `narrative_alpha/arms.py` (15 copy + 30 wire).
2. `consensus.evaluate` + ensemble aggregation (median p, agreement, dissent) with `Forecast` inlined (20).
3. `brier.py` + `wide_edge/scoring.py` settle/CI/gate (15).
4. `should_buy_judgment()` written fresh on the kelly gate skeleton (30-45).
5. Evidence ledger dataclasses (`ProviderResult` fields, `wide_edge/models.py` log entries) (20).

## 3. Machine-originated payment: state of the world (payment-findings.md)

- Stripe natively supports x402 (Base USDC) and MPP (Tempo USDC / card SPTs) as of API preview
  `2026-05-27.preview`; payments land as PaymentIntents in the merchant balance, so the organizers'
  restricted key sees them. Sample: `stripe-samples/machine-payments`.
- Blocker: the "Stablecoins and Crypto" payment method needs Stripe review. Verified live this morning
  on Aria's CLI-logged account (`acct_1TcW4QBU3SAXxA4O`, "Design ELF", charges and payouts enabled):
  `crypto` is present in the payment method configuration but `off`. It has to be requested in the
  dashboard first thing; approval time UNVERIFIED (secondary source: hours).
- Buyer side without per-purchase human tap: Coinbase Agentic Wallets (`npx awal`, session caps, native
  x402). Stripe's own Link Agent Wallet says "you approve every purchase", so it fails the thesis.
- External population: x402 is real (~197M txns, ~846k buyers per x402scan, July 2026) and Coinbase
  Bazaar indexes endpoints, but there is no evidence a fresh listing gets organic paid calls in hours.
  OpenClaw wallet/x402 skills exist on ClawHub; all are "developer wires up wallet"; no directory of
  running agents that would call a new paid tool. Answer to the existential question: NO for today.
  Listing on Bazaar costs nothing once the endpoint exists; treat any external hit as a bonus.
- Payment Link (customer chooses price) is GA, live-mode ready on the existing account, minutes to set up.

Path to first machine-originated payment (P~0.7): request crypto method -> `POST /v1/crypto/deposit_addresses
network=base` -> deploy x402 endpoint from the Stripe sample with that payTo -> fund an `awal` wallet with
~$5 USDC on Base -> our buyer agent pays -> `onAfterSettle` records the PaymentIntent. If crypto review
has not cleared by 13:00, stop spending on it: run `npx mppx validate` in sandbox as the machine-payment
demo and let the Payment Link carry the revenue.

## 4. Stripe coexistence

Yes, if payTo is a Stripe crypto deposit address: x402/MPP settle into the same Balance the organizers
read. If review is not approved, USDC would sit in a CDP wallet and would need explicit organizer
acceptance; do not rely on that. Card revenue via Payment Link is unconditional.

## 5. Terac constraints (terac-findings.md)

- MCP: `claude mcp add --transport http terac https://terac.com/api/mcp`; REST base
  `https://terac.com/api/external/v2`, `tk_` API key works headless, 100 req/min, v2 beta.
- Flow: get_context -> request_feasibility -> poll price -> create draft opportunity -> launch ->
  approve submissions. `review_type: auto_approve` avoids a manual approve step. Credits deducted on
  approval only.
- Two documented facts that threaten the whole hackathon requirement: pricing is done by a Terac human
  ("typically within about an hour") and standard audiences "fill within about a week", first completes
  "within a few days". Marketing says same-day, median under 24h. Nothing published at minutes
  granularity and nothing hackathon-specific. UNVERIFIED whether the event has an expedited genpop lane;
  the organizers' "general population for fastest results" line suggests one exists. Ask the booth,
  first question, and launch the first study before 12:00 whatever the answer.
- Survey answers are not exposed in the external submissions API. Use an `activity` task with our own
  `task_url`; Terac appends `teracSubmissionId`; we own the ratings; redirect to
  `terac.com/api/external/callback?...&result=completed` (auto-reject after 6h without callback). This
  also means the rating UI is ours and streams into the verdict as each human finishes.
- Cost per genpop response unpublished; expert examples ~$28 per task; hackathon credit link semantics
  UNVERIFIED. Terac thesis, verbatim: "AI will do most of the world's work with the help of humans",
  "the default API call for any AI system that needs to source, hire, verify, or pay a human". An agent
  that decides on its own to hire humans is their pitch on stage.
- Competitors: meatspace.so, humanrail.dev, SanctifAI, ClawHub askhuman, Magic API skill exist;
  getabrain.ai, verifi, humanrelay, pausepoint, ask-a-human, loopuman, agentdo not found. Nearest real
  analogs: HumanLayer, Cheqpoint, RentAHuman. All sell "ask a human". None sell "decide whether asking
  is worth it, then route to the cheapest sufficient source". That routing decision is the wedge.

## 6. Sponsors that are structural (sponsor-findings.md)

- Band: real coordination bus (rooms, @mention routing, WebSocket, Python/TS SDK, Claude adapters).
  Judges' delete test wants dependent handoff, runtime recruit, cross-account boundary, or a critic veto.
  Our broker -> evaluators -> human oracle -> critic flow maps to their "runtime recruit" + "critic
  overlay" patterns. STRUCTURAL, ~75 min, but only after the loop is proven end to end.
- Linq: REST iMessage/SMS, under 5 min to first send, inbound-first sandbox (human texts first, 100
  contacts, 7 days, no links in the first outbound). Text-reply-as-vote is certain; tapback webhook
  payload UNVERIFIED. STRUCTURAL as the fast in-room human tier when Terac is slow, ~40 min.
- Replay: real REST API (`loop-qa.replay.io/api/v1`), usable as an async machine evaluator for "does
  this web app work". Nice-to-have, ~45 min, only if the buyer agent builds sites.
- Superserve, sandbox0, Render workflows (no wait-for-signal primitive), Whop/Dodo (MoR, not
  Stripe-visible): skip or garnish.

## 7. Kill criteria (hard, clock-based)

- 12:00: Terac study created via API/MCP AND a price or first submission has appeared. If neither,
  Terac drops to "slow expert tier": launch it anyway for the before/after harvest at 17:00, and the
  live human tier becomes Linq in-room panel.
- 13:00: Stripe crypto method approved and a deposit address minted. If not, machine-payment lane
  becomes sandbox `mppx validate` plus Payment Link; no more crypto time.
- 15:00: at least one real charge in Stripe Balance. If not, sell the human-facing product harder
  (QR + Linq number on every table): "five real people test whether your pitch/page makes sense".
- 16:30: full round trip demonstrated once (buy -> evaluate -> disagree -> hire -> verdict -> buyer
  changes output). If not, cut Band, cut dashboard polish, demo the round trip from logs.

## 8. Recommended architecture (one process, one repo, ~1500 lines)

```
buyer agent (ours; landing-page writer)     external agents (bonus, via Bazaar/x402)
        |  POST /judge {input, question, audience, max_budget, confidence}
        v
  pricing + payment gate   Payment Link (humans) | x402 -> Stripe deposit addr (machines)
        v
  broker: N cheap-tier evaluators -> consensus.evaluate -> dissent_score
        v
  should_buy_judgment(E_loss_without, E_loss_with, price)   <- VOI rule, fail closed
        v
  evidence router (bandit over arms: ensemble | linq_panel | terac_genpop | terac_expert)
        v
  Terac opportunity (activity task -> our rating page) / Linq blast to in-room panel
        v
  aggregate -> verdict {verdict, confidence, agreement, minority_view, evidence_trail, cost}
        v
  settle: brier per evaluator vs human oracle -> update_posterior -> reputations move
        v
  ledger: revenue, evidence cost, margin, per-decision log (wide_edge dataclasses)
```

Stack: Python FastAPI (augur is Python; vendored modules drop straight in), SQLite, one static
dashboard page reading the ledger. Terac via REST with `tk_` key. Stripe via CLI-logged account.

## 9. Minimum demo (in priority order)

1. Real charge in Stripe (Payment Link) for one judgment.
2. Terac opportunity created by our agent, humans rate on our page, results aggregated.
3. Buyer agent writes landing page -> evaluators disagree -> buys judgment -> humans misread it ->
   rewrite -> second panel understands it. Before/after with numbers.
4. Machine-originated payment recorded as a Stripe PaymentIntent (our capped wallet), labelled honestly.
5. Ledger: gross, Terac cost, margin, and the "why bought" line per decision.

## 10. Fallback

Same machinery, human buyer only: QR + Linq number, "$8: five real people test whether your page makes
sense, plus the verdict". Terac still gets used for before/after; the zero-person agency shape stays in
reserve if the room proves to be the only market.

## Open questions only Aria can answer

Which Stripe account to use (the CLI-logged "Design ELF" company account is live now; a fresh individual
account costs activation time), and whether the machine-payment lane is worth its clock at all.
