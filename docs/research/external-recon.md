---
type: note
status: active
created: 2026-08-15
---

# Zero Human Company Hackathon: external recon (2026-08-15)

Prior file `_meta/research/zero-human-hackathon-sponsors.md` does NOT exist. This is fresh work,
nothing inherited. Read-only research, ~35 min.

## Answers in one line each

- **A. Terac**: Real, documented, usable today: REST v2 beta at `https://terac.com/api/external/v2`
  (Bearer API key, 100 req/min) plus a hosted MCP at `https://terac.com/api/mcp` (OAuth, 7 tools);
  the money numbers are the problem, docs' own example is **$28/expert, ETA 6h, delivered 5h12m**,
  so a 5-10 respondent question is **$140-280 and hours, not minutes**. [verified-live]
  https://terac.com/mcp | https://terac.com/docs/developers
- **B. Can an external agent pay us today?**: **Yes, via x402** (USDC on Base, CDP facilitator,
  Bazaar discovery) and that is the only self-serve path that works in an 8-hour window; Stripe's
  **Machine Payments** does accept x402/Base USDC and lands it **in your Stripe balance** (so a
  restricted read key on balance+charges would see it), but stablecoin acceptance is gated
  (US-only ex-NY, email for elsewhere) so do not bet the demo on it. [verified-live]
  https://docs.stripe.com/payments/machine | https://docs.cdp.coinbase.com/x402/bazaar
- **C. Competitors**: The exact idea is **already occupied**: **MeatSpace** (meatspace.run) and
  **HumanRail** (humanrail.dev, "Stripe for human judgment") are live and near-identical;
  **SanctifAI** is the funded incumbent (Human-as-a-Tool, MCP + on-chain attestation);
  getabrain.ai / pausepoint / loopuman / verifi show **no evidence of existing**; nobody found is
  doing **value-of-information routing** (deciding *whether* asking a human is worth it), which is
  the only unoccupied seat. [verified-live] https://meatspace.run/ | https://sanctifai.com/
- **D. Sponsors**: Linq = iMessage/RCS/SMS comms API with REST + webhooks + in-message payments
  (docs.linqapp.com); BAND = shared multi-agent interaction layer, docs.band.ai, hacker-guide is a
  quickstart to two agents in a room; Dodo = merchant-of-record, ~4% + $0.40 US domestic,
  +1.5% intl, no monthly fee; Whop MoR not verified this pass. [doc-claim]

---

## A. Terac surface (verified-live unless noted)

Two surfaces, same backend.

**MCP** `https://terac.com/api/mcp`, OAuth on first connect, no key paste. Tools:
`terac_list_opportunities`, `terac_request_feasibility` `{role, task, count}`,
`terac_get_feasibility_request` `{request_id}`, `terac_launch_draft_opportunity` `{request_id}`,
`terac_get_submissions`, `terac_get_context`, `terac_pause_opportunity`.

**REST v2 (beta)** base `https://terac.com/api/external/v2`, `Authorization: Bearer <key>`,
keys minted in org settings, 100 req/min then `429 RATE_LIMITED`. Endpoint families:
organization context; feasibility (request/get/list); projects (list/create/get/update);
opportunities (create/list/get/update/delete/**launch**/pause/resume/stop); submissions
(list/get/**approve**/reject); filters (getFilters, getFilterOptions); webhooks (full CRUD +
signing secret + rotate + deliveries).

**Flow**: request feasibility (role + task + count) -> get a quote (`cpi_usd`, price, eta) ->
launch draft opportunity -> submissions arrive -> approve/reject -> billed only on approved.

**Results**: webhooks are the documented path. Events `submission.status.change` and
`submission.approved`; payload `{event_type, event_id, resource_id, occurred_at, opportunity_id,
from, to}`; HMAC-SHA256 as `X-Terac-Request-Signature` = base64(HMAC(secret, timestamp + raw
body)), with `X-Terac-Request-Timestamp` and a retry-stable `X-Event-ID`. Docs say "instead of you
polling", but `listSubmissions` exists, so **polling works fine for a hackathon demo** and skips
the public-endpoint problem. [verified-live docs, unverified in practice]

**Cost + latency, the load-bearing risk.** Panel is explicitly a **verified expert** panel
(8k software, 7.5k education, 3k SMB owners), "not crowdworkers". Marketing says "median
launch-to-result under 24h"; the MCP page's own worked example is `cpi_usd: 28`, quote
"$84 - eta 6h", delivery "5h 12m". No general-population cheap tier found in docs.
**Implication: 5-10 respondents = $140-$280 and ~5-6h.** That is fatal to a "$0.50-$5 API call"
price point and to any live-demo turnaround. [verified-live for the example numbers;
**unverified** whether a cheaper general-pop tier or faster small-n path exists, ask Terac staff
on site, this is the single highest-leverage question of the day]

## B. Autonomous external payment

**Fastest working path**: price your endpoint in x402. External agent hits it, gets HTTP 402 with
payment requirements, pays USDC on Base, retries with the receipt as credential. No account, no
subscription, no human at purchase time. Discovery is solved too: the **CDP Bazaar** indexes
x402 endpoints and agents search it by intent, plus OpenClaw/ClawHub skills (`openclaw-x402-skill`,
`skillzmarket`, `agentcash wallet`) already do browse-and-pay with a funded EVM key. Coinbase
shipped **Agentic Wallets** (Feb 2026, gasless Base, TEE keys); x402 governance moved to the Linux
Foundation (Apr 2026, 22 members incl. Google, Visa, Stripe, Circle); Coinbase claims ~69k active
agents. Treat the transaction counts as inflated by farming. [verified-live docs + doc-claim stats]

**Stripe visibility**: `docs.stripe.com/payments/machine` states payments "land directly in your
Stripe balance and settle in fiat", refunds via Refunds API, min **0.01 USDC** for stablecoin
(0.50 USD for card SPTs). Supported: MPP on Tempo/Solana, **x402 on Base**. So yes, a restricted
read-only key on balance + charges would see the money **if** you are enabled. Gate: stablecoins
available to US businesses except New York; outside US you must email machine-payments@stripe.com.
[verified-live]

**Other rails**: MPP (Stripe + Tempo, Mar 2026) adds pre-authorized spend sessions and streamed
micropayments across fiat and stablecoin, and is Stripe's preferred path; ACP (OpenAI + Stripe)
is checkout for shopping, not per-call API billing; AP2 (Google) is a mandate/authorization
framework, not a per-call rail. For an $0.50-$5 API call bought by a stranger's agent today:
**x402 first, MPP second, everything else is not it.**

## C. Competitors

| Name | Status | What it does |
|---|---|---|
| **MeatSpace** (meatspace.run) | live | HITL API "when agents need subjective human judgment"; taste, approval, preference, tie-breaks. REST + MCP + TS/Python SDKs. **This is our pitch, verbatim.** |
| **HumanRail** (humanrail.dev) | live | Routes to vetted humans, verifies, pays the worker, returns structured response. Self-described "Stripe for human judgment". |
| **SanctifAI** (sanctifai.com) | live, funded | Human-as-a-Tool / Human-as-a-Model. Four modalities: verification, escalation, consultation, simulation. Two-sided marketplace, reputation, agent budgets, on-chain attestation, MCP + API. The serious incumbent. |
| **AskHuman** (askhuman.net + askhuman.guru) | live | Context engine from human decisions; worker platform pays humans in **USDC** for agent-requested judgment. |
| **HumanLayer** (YC F24, 11k+ stars) | live, pivoted | Started as the HITL approval SDK, now an agent-coding IDE. Vacated the lane. |
| **AgentDo** (agentdo.dev) | live | "Craigslist for agents", agents post tasks other agents do. Not human judgment. |
| **Agent Relay** (agentrelay.com) | live | Headless Slack for agents with human approval pauses. Infra, not a judgment marketplace. |
| **Rent Human AI**, **HumanAgent** | live | Hire humans for physical tasks / human checkpoints. Adjacent. |
| getabrain.ai, verifi, pausepoint, loopuman | **no evidence** | Nothing found. Do not cite these as competitors. |

**Value-of-information / uncertainty routing**: no startup found selling this. What exists is
confidence-threshold escalation inside support products (Intercom Fin publishes real research on
escalate-vs-answer) and generic handoff-pattern blogging. **Nobody is selling "was this question
worth $12 of human time?" as a product.** That is the differentiated wedge, and it is also the
part that makes expensive slow Terac responses defensible: you only buy humans when the decision
value justifies it.

## Verdict for the build

The demo-killer is not payments, it is Terac's economics: **$28/response and ~6h** versus a
$0.50-$5 autonomous purchase. Either find a cheap general-population tier (ask on site, first
thing), or reprice the product as a high-value judgment call ($50-$200, VOI-gated) and accept an
async webhook-delivered verdict rather than a live round trip. Sell the routing decision, not the
survey.

## Sources
- https://terac.com/mcp | https://terac.com/docs/developers | .../reference | .../guides/webhooks | .../guides/authentication | https://terac.com/ai
- https://docs.stripe.com/payments/machine | https://docs.cdp.coinbase.com/x402/bazaar | https://www.coinbase.com/developer-platform/discover/launches/x402
- https://www.crossmint.com/learn/agentic-payments-protocols-compared | https://cloud.google.com/blog/products/ai-machine-learning/announcing-agents-to-payments-ap2-protocol
- https://meatspace.run/ | https://humanrail.dev/ | https://sanctifai.com/ | https://www.askhuman.net/ | https://www.agentdo.dev/ | https://www.ycombinator.com/companies/humanlayer
- https://fin.ai/research/to-escalate-or-not-to-escalate-that-is-the-question/
- https://docs.linqapp.com/ | https://www.band.ai/hacker-guide | https://dodopayments.com/blogs/payment-api-guide
