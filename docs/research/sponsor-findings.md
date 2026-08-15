---
type: research
status: active
created: 2026-08-15
---

# Sponsor findings for "judgment-for-agents" (Zero Human Company Hackathon, 2026-08-15)

Read-only web pass, ~15 min. UNVERIFIED = docs not reachable or silent on the point.

## 1. Band (band.ai)
- What: "Discord for AI agents". Agents (any framework, run on YOUR infra) get persistent identity, share chat rooms, route work via @mentions, WebSocket (Phoenix Channels) at wss://app.band.ai/api/v1/socket/websocket. Primitives: Agent, Chat room, @mention, Contact (bilateral permission), Execution.
- SDK: Python `band-sdk` (uv add "band-sdk[anthropic]" etc.), TS `@band-ai/sdk`. Adapters for LangGraph, Anthropic SDK, Claude Agent SDK, Codex, Pydantic AI, CrewAI, ... Agent API: GET /me, /peers, /chats; POST /chats/{id}/messages, /participants, /events. LLM-exposed tools: band_send_message, band_send_event, band_add_participant, band_lookup_peers, band_create_chatroom.
- Free tier: 10 agents, full API. Quickstart claims 5 min per agent (register in dashboard -> UUID + key -> yaml -> Agent.create(adapter).run()).
- "Meaningful use" = Delete Test, need at least one: (1) dependent handoff via @mention, (2) runtime roster via band_lookup_peers + band_add_participant, (3) enforced boundary (cross-account/contacts), (4) blockable verdict (critic agent vetoes). NOT counted: status pings, one process switching personas, orchestrator calling agents in sequence, dashboard as deliverable. Submission wants a one-line flow + Who / who-talks-to-whom / delete test.
- Fit: buyer -> @Broker -> @Evaluator1..N (recruited per case via lookup_peers = pattern 2) -> @HumanOracle (human user in the room, pattern "end on human approval/block") -> @Critic can veto (pattern 4). This maps almost 1:1 to their patterns "Runtime recruit" + "Critic overlay" + "Panel". Each role must be its own registered agent_id.
- Risk: our EV gate / Terac human hire must live in the broker agent's tool set, not outside the room, or it fails "orchestrator calling in sequence".
- URLs: https://www.band.ai/hacker-guide, https://docs.band.ai/, https://docs.band.ai/integrations/adapters, https://github.com/band-ai
- Verdict: STRUCTURAL (it can be the actual bus). ~60-90 min for 3-4 agents incl. registration; 1 hour is tight but plausible with the Anthropic adapter.

## 2. Linq (linqapp.com/hackathon)
- What: iMessage/RCS/SMS REST API. POST /api/partner/v3/chats (new chat), POST /v3/chats/{chat_id}/messages, POST /v3/messages (auto line pick), POST /v3/webhook-subscriptions. TS SDK `@linqapp/sdk`. Bearer auth. Quickstart says <5 min to first message.
- Webhooks: message.sent/received/delivered/read/failed. Marketing + third-party writeups say tapback reactions, typing, read receipts are delivered via webhooks and agents can SEND tapbacks; the exact reaction webhook payload was NOT confirmed in the docs I could reach (UNVERIFIED, check https://docs.linqapp.com/api/ webhook reference).
- iMessage Apps: `imessage_app` message part (team_id, bundle_id, url, layout captions), card can be updated in place via /messages/{id}/update. Requires a Messages extension identity; no vote/approval template documented; button-tap callback format UNVERIFIED. Treat as decorative for a hackathon.
- Sandbox constraints: inbound-first (human must text the number first), 100 contacts, number valid 7 days, first outbound message may not contain links/reply_to/effects.
- Fast path: room humans text the number -> webhook -> we register them as oracles -> we text a question -> reply text or tapback = vote. Inbound-first rule actually helps (opt-in). Tapback-as-vote is UNVERIFIED payload but text-reply-as-vote is certain.
- URLs: https://linqapp.com/hackathon, https://docs.linqapp.com/getting-started/quickstart/, https://docs.linqapp.com/api/, https://linqapp.com/blog/supercharge-your-agents-with-imessage-apps
- Verdict: STRUCTURAL as the human-oracle channel (real humans in room, phone in hand). ~30-45 min (signup, one POST, one webhook endpoint via ngrok/render).

## 3. Replay QA (qa.replay.io)
- What: autonomous QA agent: give it a URL, it explores, tests, records (time-travel), returns bug reports w/ root cause + suggested fix, can emit Playwright tests. Auth flows + localhost via reverse proxy.
- Programmatic: YES. REST API https://loop-qa.replay.io/api/v1, OpenAPI at /api/v1/openapi.json, bearer `lqa_...`. Flow: create project (target_url + note on key flows) -> poll status -> fetch bug reports. Free 25 credits/mo, no card. Time-to-first-result UNVERIFIED (likely many minutes, async).
- Fit: an "evidence source" evaluator agent for the question "does this web app work?" It is a legit machine oracle before spending on humans. Latency makes it a background job, not a synchronous verdict.
- URLs: https://qa.replay.io, https://docs.replay.io/basics/replay-qa/overview, https://www.replay.io/blog/replay-qa
- Verdict: NICE-TO-HAVE (structural only if a demo verdict is about a web app). ~45 min incl. async polling; demo risk from run latency.

## 4. Superserve (superserve.ai) and sandbox0
- Superserve: durable Firecracker microVMs for long-horizon agents; pause indefinitely / resume / snapshot / fork; TS SDK `Sandbox.create -> commands.run -> pause()`; preview URLs, MCP, Docker; per-second billing, free tier no card; open source/self-hostable. Docs https://docs.superserve.ai.
- sandbox0: open-source sandbox for AI agents (github.com/sandbox0-ai/sandbox0, sandbox0.ai): stateful sessions, volumes/snapshots/fork, network allow/deny + credential injection, warm pools, "Managed Agents" Claude-compatible API shape.
- Fit: our service is request/response + a wait-for-humans queue; nothing needs a persistent VM. Only plausible use: run each evaluator agent (or the thing under judgment) in an isolated VM. Decorative for us.
- URLs: https://superserve.ai, https://docs.superserve.ai, https://sandbox0.ai/, https://github.com/sandbox0-ai/sandbox0
- Verdict: SKIP (would be padding). 30+ min for zero structural gain.

## 5. Render Workflows
- What: public beta; managed orchestration for long-running distributed tasks: define tasks as SDK functions (TS/Python), chain by calling task functions, trigger via SDK/REST/CLI/dashboard, each run in its own on-demand instance up to 24h, retries, scale-to-zero. Limits: no scheduling (use cron), runs cannot receive inbound connections, TS/Py only.
- Human-in-loop: docs show NO native "wait for external event / signal" primitive (unlike Temporal/Inngest). A "job -> wait for humans -> aggregate" workflow would have to poll a DB / sleep-loop inside a 24h run, or be split into two runs triggered by our webhook receiver. Workable but not the natural fit the name suggests.
- URLs: https://render.com/docs/workflows, /docs/workflows-tutorial, /docs/workflows-defining, /docs/workflows-running, /docs/workflows-limits
- Verdict: NICE-TO-HAVE (host the service on Render regardless; Workflows only if we want durable EV-recompute/aggregate jobs). ~45-60 min; polling hack needed for the human wait.

## 6. Whop and Dodo Payments
- Whop: REST https://api.whop.com/api/v1, SDKs TS/Python/Ruby, API key or OAuth; programmatic checkout configs, sub-merchant onboarding, payouts, verification URLs, payment methods incl. crypto/apple_pay/bank. Marketplace/platform flavour. Credits/usage billing and MoR status not stated on the getting-started page (UNVERIFIED). https://docs.whop.com/developer/api/getting-started
- Dodo: explicit global Merchant of Record (190+ countries, 30+ methods); SDKs in 9 langs; products, checkout sessions, one-time/subscriptions, usage-based billing (meters + usage events), credit systems, webhooks, test vs live hosts (test.dodopayments.com / live.dodopayments.com). Best match for "sell API credits". https://docs.dodopayments.com, https://docs.dodopayments.com/api-reference/introduction
- Stripe visibility: neither doc mentions Stripe under the hood; as MoR the sale is THEIR sale, so revenue would land in Dodo/Whop dashboards and payouts, NOT in our Stripe. Assume not Stripe-visible (UNVERIFIED for Whop internals).
- Fit: buyer agent pays per verdict. Dodo usage-based meter or credit pack is a clean fit; Whop is more creator/marketplace-shaped.
- Verdict: NICE-TO-HAVE, pick Dodo if we want a sponsor payments story (~30-45 min, test mode). If the hackathon judges revenue via Stripe, SKIP both and use Stripe directly.

## Priority stack for a <1 day build
1. Band as the coordination bus (STRUCTURAL, ~75 min)
2. Linq as the human-oracle channel (STRUCTURAL, ~40 min)
3. Dodo test-mode credit meter (NICE, ~40 min) or Stripe if judged there
4. Replay QA as an automated evaluator for web-app claims (NICE, ~45 min, async)
5. Render Workflows only for aggregation jobs (NICE, ~60 min); Superserve/sandbox0 SKIP
