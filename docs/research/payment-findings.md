---
type: research
status: active
created: 2026-08-15
---

# Machine-payment findings: can an EXTERNAL agent pay us today? (2026-08-15, 25-min web pass)

## VERDICT

- **"A genuinely external agent discovers and pays our new endpoint within ~3 hours": NO-GO as a plan, weak MAYBE as a bonus.**
  Rails exist and are GA (x402 on Base has ~200M txns / ~850k buyers per x402scan late July 2026), and Coinbase Bazaar auto-indexes x402 endpoints, but I found NO primary evidence that a brand-new listing gets organic paid calls from unknown agents within hours. Treat organic external payment as a lottery ticket, not the demo.
- **"Machine-originated payment lands in OUR Stripe Balance/Charges today": CONDITIONAL GO.**
  Stripe now natively supports x402 (Base USDC) and MPP (Tempo USDC / card SPTs); payments become PaymentIntents in your Stripe balance. Blocker: the **"Stablecoins and Crypto" payment method needs a Stripe review** (shows Pending; timeline UNVERIFIED for a fresh personal account; one secondary source says "hours" for US merchants after KYB). Card-SPT path avoids crypto review but the buyer wallet (Link Agent Wallet) is human-approve-per-purchase today.
- **Credible fallback (recommended primary demo): a buyer agent WE run on a separately funded Coinbase Agentic Wallet with policy-set spend caps, no per-purchase human approval, paying our x402 endpoint whose payTo is a Stripe deposit address.** Machine-originated: yes. External: no; say so honestly. Judges see the PaymentIntent in Stripe.

## 1. Stripe-native machine payment paths (Aug 2026)

| Path | GA? | Lands in Stripe Balance/Charges? | Setup | Activation / KYC | Test vs live |
|---|---|---|---|---|---|
| **MPP** (Stripe+Tempo, launched 2026-03-18) via `mppx` server + `stripe.create` | Yes, docs public; API version `2026-05-27.preview` header | Yes: mppx auto-creates PaymentIntents (SPT immediately; Tempo via `transaction_verification` after on-chain settle) | ~15 lines; `npm i mppx stripe`; `npx mppx@latest validate` does roundtrip test payments | Crypto leg: request "Stablecoins and Crypto" payment method, Stripe reviews (Pending). Fiat/SPT leg: needs Stripe **profile** (`profile_` id), US/CA legal entity, min $0.50 | Sandbox: `profile_test_`, Tempo testnet auto; live moves real funds |
| **x402 on Stripe** (Base USDC) | Yes, docs public (preview API version) | Yes: you create `/v1/crypto/deposit_addresses network=base`, set as payTo, then record PaymentIntent with `payment_method_types:["crypto"]`, `mode: transaction_verification`, tx hash | Needs CDP account + API keys (Coinbase facilitator settles mainnet), `@x402/*` + `@coinbase/x402` + stripe; sample repo stripe-samples/machine-payments | Same "Stablecoins and Crypto" review; US except NY, or email machine-payments@stripe.com | Live only in practice for mainnet (deposit address in live mode) |
| **Shared Payment Tokens (SPT)** | GA (Etsy, URBN live) | Yes, PaymentIntent with the token | Part of MPP fiat leg | Profile + US/CA entity | Sandbox supported |
| **Link Agent Wallet** (buyer side, link.com/agents; `@stripe/link-cli mpp pay`) | Beta-ish; "granular controls coming soon" | n/a (buyer) | `npx @stripe/link-cli auth login` then `mpp pay <url>` | Page says **"You approve every purchase"** in the Link app: fails the "no human approves the specific purchase" test. UNVERIFIED whether link-cli can pre-authorize | works with sandbox |
| **Payment Links** ("customer chooses price") | GA | Yes | minutes | account activation only | live needs activation |
| **Stripe Agent Toolkit** (`@stripe/agent-toolkit`) | GA | It creates Payment Links / invoices; the payer is still a card holder. Does not make an agent a payer by itself | minutes | n/a | both |
| **Stripe Issuing virtual card for our buyer agent** | Issuing exists, but Issuing activation is a separate business application/review. UNVERIFIED for same-day on a personal account; assume not available in 3 h | Would land as normal card charge (and Stripe may flag self-dealing) | | Issuing application | |
| Stripe joined **x402 Foundation** (Linux Foundation, July 2026, 40 members) | context only | | | | |

Sources: https://docs.stripe.com/payments/machine · https://docs.stripe.com/payments/machine/x402 · https://docs.stripe.com/payments/machine/mpp · https://stripe.com/blog/machine-payments-protocol · https://mpp.dev/ · https://link.com/agents · https://github.com/stripe-samples/machine-payments · https://stripe.com/blog/supporting-additional-payment-methods-for-agentic-commerce

## 2. Non-Stripe machine rails

- **x402 (Coinbase, USDC on Base)**: GA, big live population (x402scan late-July 2026: ~197M txns, $52M volume, ~846k buyers, ~253k sellers; Base >90%; Chainalysis "100M agentic payments on Base"). Discovery: **Coinbase Bazaar** (public REST/SDK/MCP: `searchX402Resources`, `listX402DiscoveryResources`), Agentic.Market, x402scan indexer, third-party x402bazaar.org (69 endpoints, "listed 30-60 s after first settled payment"). Reconcile into Stripe: yes if payTo is a Stripe crypto deposit address (section 1); otherwise it sits in a CDP/EOA wallet and organizers must accept it separately.
  https://docs.cdp.coinbase.com/x402/bazaar · https://www.chainalysis.com/blog/x402-agentic-payments-adoption/ · https://note.com/x402inc/n/n508ffae4a764 · https://www.x402bazaar.org/
- **Coinbase Agentic Wallets** (2026-02-11): MPC wallet for agents, session caps + per-tx limits set by operator up front, **no per-transaction human approval**, native x402, `npx awal` CLI / MCP for Claude/Codex/Gemini. Best buyer-side tool for the fallback demo. https://www.coinbase.com/developer-platform/discover/launches/agentic-wallets · https://docs.cdp.coinbase.com/agentic-wallet/cli/welcome
- **Google AP2, Visa Intelligent Commerce, Mastercard Agent Pay**: mandate/credential standards for consumer-agent checkout; no self-serve "list your API, agents pay" path found in this pass. UNVERIFIED depth. https://www.crossmint.com/learn/agentic-payments-protocols-compared
- **Skyfire, Nevermined, PayOS, agentpayy, the402, Cloudflare pay-per-crawl**: not verified this pass (time). Cloudflare is an x402 Foundation member; pay-per-crawl targets crawlers, not API buyers. Mark all UNVERIFIED.
- Crossmint **lobster.cash** (with Visa, Circle, Solana, Stytch): open payment standard for OpenClaw agents. UNVERIFIED liveness.

## 3. OpenClaw / ClawHub state

- ClawHub hosts ~5,700+ skills. Payment-relevant skills found: `openclaw-x402-skill` (browse Bazaar; browse+pay mode needs `EVM_PRIVATE_KEY` + funded Base wallet), `x402-enhanced`, `xClaw02`, Privy agentic-wallets skill, Coinbase Agentic Wallet integration (Frankyfliu/openclaw-coinbase-agentic-wallet), Link Agent Wallet skill.md ("Works with Claude, OpenClaw, custom agents"). Install counts: not captured, UNVERIFIED.
- Autonomous spend: yes, by policy (spend caps like "auto-approve under $50", 5 exec/min backstops), when the operator has funded a wallet and installed a skill.
- Distinction: **all evidence is "developer wires up wallet + skill"; there is no public directory of running OpenClaw agents that would call a new paid tool unprompted.** Discovery would go through the Bazaar-browsing skill, if an agent is tasked with something our tool answers.
  https://clawhub.ai/coinvest518/openclaw-x402-skill · https://github.com/BlockRunAI/awesome-OpenClaw-Money-Maker · https://github.com/privy-io/privy-agentic-wallets-skill

## 4. Ranked path to a FIRST machine-originated payment in ~3 h

1. **(P≈0.7) x402 endpoint, payTo = Stripe Base deposit address, buyer = our own Coinbase Agentic Wallet with policy caps.** Steps: activate Stripe (individual), request "Stablecoins and Crypto" immediately (Pending gate!), `POST /v1/crypto/deposit_addresses network=base` (preview header), CDP account + keys, deploy sample from stripe-samples/machine-payments, `npx awal` wallet funded with $5 USDC on Base, agent calls endpoint, `onAfterSettle` records PaymentIntent. Blockers: crypto review pending (if not approved, deposit address call may fail: UNVERIFIED), CDP KYC for API keys is quick.
   Credibility to judges: honest "machine-originated, policy-bounded, not human-approved per purchase; buyer wallet is ours". Say it plainly.
2. **(P≈0.5) MPP with mppx, same Stripe crypto gate, plus card SPT leg.** `npx mppx validate` in sandbox proves the flow in minutes; live SPT payer = link-cli, but human taps approve in Link app (weaker story). Tempo CLI (`tempo wallet fund`) can be the crypto payer.
3. **(P≈0.3 as ADD-ON) List in Coinbase Bazaar / x402scan / x402bazaar.org and hope an external agent pays.** Zero cost once (1) is live; set `discoverable`/description well; watch Stripe Payments for a payer address that is not ours. Do not promise it.
4. **(P≈0.9 for money, ≈0 for "agent buyer") Payment Link fallback.** Always have it: revenue visible for sure; agent role limited to *creating* the link (Agent Toolkit).
5. **(P<0.1) Stripe Issuing card for our agent**: skip.

## 5. Stripe live mode for a brand-new personal account

- Test/sandbox works with no details. Live requires **activation**: legal name, address, tax id (SSN last 4 for individual), bank account. For US individuals activation is typically instant; **you can accept charges while verification continues, payouts are held (first payout 7-14 days)**. Stripe may later request docs. So "personal account, no business verification for small payments" = choose Individual/Sole proprietor, activate, charges flow; Balance shows funds; payouts lag. Restricted key reading Balance + Charges works in live mode.
- Separate gates NOT covered by plain activation: "Stablecoins and Crypto" payment method review (needed for x402/MPP crypto legs), Stripe **profile** for SPT, US/CA entity for SPT.
  https://docs.stripe.com/get-started/account/activate · https://wise.com/us/blog/stripe-sole-proprietor · https://support.stripe.com/questions/get-started-with-stablecoin-payments

## Open UNVERIFIED items (check first thing)
- How long "Stablecoins and Crypto" review takes for a fresh individual account, and whether `crypto/deposit_addresses` returns before approval.
- Whether `link-cli mpp pay` can run without a per-purchase tap.
- Bazaar listing latency and any organic traffic to fresh endpoints.
- Skill install counts on ClawHub; Skyfire/Nevermined/PayOS/the402 status.
