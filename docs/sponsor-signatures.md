---
type: reference
status: active
created: 2026-08-15
issues: [4, 24]
sources: each sponsor's own docs (URLs per entry), guidebook pages 15-36, our own live Terac MCP session
---
# Sponsor signatures: what real use looks like, per the sponsor's own docs

Detection first (zero model calls), then the panel judges `meaningful_use` from evidence with quotes.
Signatures are checked over: repo file tree, manifests (package.json, pyproject, requirements),
source files, env example files, config files (render.yaml, *.yaml), README, deck text, page text.
`code` hits count as strong; `text` hits alone are weak (deck can say anything).
No hits at all = `not used` (no model call). Hits + majority yes on `meaningful_use` = `qualifies`.
Hits + otherwise = `claimed, not evidenced`, fix = the failed statement. `fake_tells` are checked as
negative evidence and quoted when they fire.

```json
{
 "terac": {"required": true,
  "code": ["terac.com/api/external/v2", "terac.com/mcp", "terac.com/api/mcp", "TERAC_API_KEY", "TERAC_PROJECT_ID", "terac_get_context", "terac_create_opportunity", "terac_launch_draft_opportunity", "terac_request_feasibility", "terac_get_submissions", "terac_approve_submission", "terac_get_opportunity", "/opportunities/", "/launch", "/submissions/", "/feasibility/requests", "api/external/callback", "teracSubmissionId", "num_participants", "screening_questions", "unrestricted_audience"],
  "text": ["Terac", "expert MCP", "general population", "launch a study", "screening question", "feasibility", "human in the loop", "before/after"],
  "meaningful_use": ["A launch call (MCP tool or POST /opportunities + /launch) exists in code, not only a key", "Real responses were collected during the hackathon (submissions read back, not seeded)", "The product or the verdict changed because of those responses and the pitch shows the delta", "The study targets the general population or says why not"],
  "fake_tells": ["TERAC_API_KEY present but no create/launch call", "hardcoded or mocked expert feedback", "no before/after shown"],
  "cheapest_honest_add": "One MCP call: terac_create_opportunity (b2c, n=3, activity task pointing at your own page) + terac_launch_draft_opportunity, then read submissions and change one thing. terac.com/docs/developers"},
 "stripe": {"required": true,
  "code": ["buy.stripe.com", "checkout.stripe.com", "stripe.com/pay", "client_reference_id", "checkout.session.completed", "stripe.Webhook", "STRIPE_", "rk_", "payment_link", "Payment Link", "import stripe", "from stripe", "\"stripe\":"],
  "text": ["Stripe", "Payment Link", "restricted key", "read-only key", "Stripe Atlas"],
  "meaningful_use": ["ONE Payment Link is used for every transaction (not regenerated mid-day)", "The account is a personal account created for the hackathon and its details + rk_ read-only key were submitted", "A stranger can pay through the link right now", "At least one payment went through today, or the pitch says the number honestly"],
  "fake_tells": ["sk_ secret key referenced where rk_ is expected", "payment link exists but nothing sends it", "several payment links"],
  "cheapest_honest_add": "Dashboard only: create Payment Link, create restricted key (Balance + Charges read), submit both. Guidebook pages 27-31. 10 min."},
 "linq": {"required": false,
  "code": ["@linqapp/sdk", "linqapp", "api.linqapp.com", "/api/partner/v3", "/v3/chats", "/v3/messages", "/v3/webhook-subscriptions", "/v3/payment_requests", "/v3/messages/", "/reactions", "LINQ_API_KEY", "LINQ_WEBHOOK_SECRET", "webhook-signature", "message.received", "message.sent", "payment.succeeded", "\"experience\"", "agentpay", "agentcard", "typing"],
  "text": ["Linq", "iMessage", "RCS", "SMS", "tapback", "iMessage App", "Agent Pay", "AgentCard", "typing indicator", "read receipt", "group chat", "blue bubble"],
  "meaningful_use": ["A real phone number is provisioned and a human texts it first (inbound webhook exists)", "The thread is where a customer or human-in-the-loop acts (buys, votes, replies), not a one-way notification", "A messaging primitive is used as UI (tapback = vote, typing = loading, group thread = lobby, iMessage App card, or Agent Pay)", "The flow is specific to a vertical, not a generic assistant"],
  "fake_tells": ["only POST /v3/messages with no webhook receiver", "Agent Pay in the deck but no payment_requests call", "iMessage App claimed but no experience part"],
  "cheapest_honest_add": "Sandbox signup at linqapp.com/hackathon, one POST /v3/chats/{id}/messages plus one webhook subscription for message.received. docs.linqapp.com/getting-started/quickstart. 30 min."},
 "replay": {"required": false,
  "code": ["loop-qa.replay.io", "qa.replay.io", "REPLAY_API_KEY", "lqa_", "/api/v1/projects", "replay_client", "replay.io"],
  "text": ["Replay", "Replay QA", "bug report", "root cause", "clean report", "false positive"],
  "meaningful_use": ["The team's own deployed URL was submitted to Replay QA during the hackathon", "Bugs it found were fixed in the repo (a commit or diff shows it)", "A re-run shows a clean or improved report (the track criterion)", "Bonus: it is called programmatically (API or MCP) as part of the build loop"],
  "fake_tells": ["key configured, no project created", "bug screenshot with no fix commit", "clean report claimed without a second run"],
  "cheapest_honest_add": "Sign up with code HACKATHON, one project against your live URL, fix, re-run. docs.replay.io/basics/replay-qa/overview. 45 min (async)."},
 "superserve": {"required": false,
  "code": ["@superserve/sdk", "superserve", "SUPERSERVE_API_KEY", "ss_live_", "Sandbox.create", "commands.run", ".pause(", ".resume(", "docs.superserve.ai"],
  "text": ["Superserve", "microVM", "Firecracker", "sandbox", "pause and resume", "snapshot"],
  "meaningful_use": ["Agents execute code, bash, or a browser inside a Superserve sandbox at runtime (a core part of the stack, per the track rule)", "pause/resume or snapshot is used between turns", "Removing Superserve would break execution, not move it local"],
  "fake_tells": ["SDK imported, one sandbox created at startup and never used", "shell commands run locally while a sandbox idles", "no pause/resume anywhere"],
  "cheapest_honest_add": "Sandbox.create() + one commands.run() for a real agent action. docs.superserve.ai/quickstart.md. 30 min."},
 "pioneer": {"required": false,
  "code": ["pioneer.ai", "api.pioneer.ai", "agent.pioneer.ai", "PIONEER_API_KEY", "fastino", "GLiNER", "GLiGuard", "gliner", "/felix/training-jobs", "base_url=\"https://api.pioneer", "qwen", "gemma", "llama", "glm"],
  "text": ["Pioneer", "Fastino", "open-weight", "GLiNER2", "GLiGuard", "fine-tune", "open model"],
  "meaningful_use": ["An inference call is routed through Pioneer's endpoint to an open-weight model (base_url points at Pioneer; model id is open-weight)", "Bonus: GLiNER2 / GLiGuard / GLiNER2-PII invoked for extraction or moderation, or a fine-tune job created", "The pitch says why an open model was the right call (cost, privacy, control)"],
  "fake_tells": ["credits redeemed but base_url never points at Pioneer", "open-weight claimed while the model id is Claude/GPT"],
  "cheapest_honest_add": "Point an existing OpenAI-shaped client at Pioneer and call one open-weight model for a real task. docs.pioneer.ai. 20 min."},
 "band": {"required": false,
  "code": ["band-sdk", "@band-ai/sdk", "band.ai", "app.band.ai", "wss://app.band.ai", "band_send_message", "band_send_event", "band_add_participant", "band_lookup_peers", "band_create_chatroom", "BAND_API_KEY", "/chats/", "/participants", "docs.band.ai"],
  "text": ["Band", "chat room", "@mention", "handoff", "runtime recruit", "critic", "veto", "delete test", "agents talking to agents"],
  "meaningful_use": ["Coordination happens in a Band chat room via @mentions and removing the room breaks the project (their delete test)", "At least one real dependency: a handoff that changes an answer, a specialist added at runtime (band_lookup_peers + band_add_participant), an enforced boundary between accounts, or a verdict one agent can block", "Each role is its own registered agent, not one process switching personas", "The submission states the one-line flow and who talks to whom"],
  "fake_tells": ["Band used as a status log", "one process switching personas", "orchestrator calling agents in sequence outside the room (named as not counting in their docs)"],
  "cheapest_honest_add": "Register 2 agents, band_lookup_peers to recruit a specialist at runtime, band_send_message for a handoff that changes the outcome. band.ai/hacker-guide. 60-90 min."},
 "render": {"required": false,
  "code": ["onrender.com", "render.yaml", "RENDER_API_KEY", "api.render.com", "render workflows", "@renderinc/sdk", "render_sdk", "workflow", "type: worker"],
  "text": ["Render", "Render Workflows", "task run", "hosted on Render", "scale to zero"],
  "meaningful_use": ["The project is deployed on Render and the live URL works", "TRACK RULE: a Render Workflows service exists with at least two chained tasks and was triggered during the hackathon", "The deploy is reproducible (render.yaml or documented settings)"],
  "fake_tells": ["plain web service, zero Workflows service", "a single trivial task added to check the box"],
  "cheapest_honest_add": "One two-task workflow (fetch -> aggregate) per render.com/docs/workflows-tutorial, triggered once via CLI/API. 45-60 min. Hosting alone does not qualify for the track."},
 "lovable": {"required": false,
  "code": ["lovable.app", "lovable.dev", "lovable-uploads", "gpteng.co", "\"lovable\""],
  "text": ["Lovable", "vibe coded", "built with Lovable"],
  "meaningful_use": ["The customer-facing surface was built with Lovable and is live", "It talks to the team's own backend or payment link, not a static mock"],
  "fake_tells": [],
  "cheapest_honest_add": "No track; credits only (guidebook page 32)."},
 "whop": {"required": false,
  "code": ["@whop/sdk", "whop-sdk", "whop_sdk", "WHOP_API_KEY", "api.whop.com", "checkoutConfigurations.create", "checkout_configurations", "mcp.whop.com"],
  "text": ["Whop", "checkout configuration", "sub-merchant", "payout"],
  "meaningful_use": ["A real checkout configuration or product exists via the API and is used to sell part of the business"],
  "fake_tells": ["WHOP_API_KEY with zero API calls", "logo in README only"],
  "cheapest_honest_add": "No track; one checkoutConfigurations.create() for a real product. docs.whop.com/developer/api/getting-started. 20-30 min."}
}
```

Notes: Terac MCP tool names are verified from our own live MCP session today; Terac REST paths from
`terac.com/docs/developers/reference`. Render Workflows SDK import names are UNVERIFIED (docs fetch was
thin); the render.yaml `workflow` service key is the strongest signal we could confirm from the tutorial
prose. Linq iMessage App button-tap payload and Whop webhook event names UNVERIFIED and not used as
signatures.
