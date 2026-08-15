---
type: research
status: active
created: 2026-08-15
---

# Terac findings (live web, 2026-08-15, ~25 min, read-only)

Note: docs.terac.com does NOT resolve (ENOTFOUND). Docs live at https://terac.com/docs/... . Everything below is from terac.com pages fetched today unless marked UNVERIFIED.

## Pitfalls first (what will bite at a hackathon)

1. **Pricing is human-in-the-loop, not instant.** MCP overview: "A person prices it, typically within about an hour, longer for niche or multi-market audiences." Workflow is "Get context -> Request feasibility -> Poll for price -> Create draft -> Launch -> Approve & pay". Budget an hour of dead time before launch, or check whether standard/genpop audiences get an instant quote (UNVERIFIED; the API also references `POST /v2/quotes`). https://terac.com/docs/researchers/mcp
2. **Fill latency is days, not minutes, per official docs.** Feasibility page: standard audiences "typically fill within about a week", first completes "within a few days of launch"; niche 1-2 weeks. Marketing pages say "same day" / "median launch-to-result under 24 hours" (interviews). No published minutes-level number. Hackathon "general population for speed" is organizer guidance, not documented SLA. Design for a small N (5-20) and be ready to show partial results. https://terac.com/docs/researchers/recruitment/feasibility , https://terac.com/user-research , https://terac.com/platform
3. **Survey answers are NOT in the external API submission schema.** OpenAPI `Submission` exposes id, status, participant_id, screening_answers, tasks[{sequence,task_type,status}], dashboard_url. Survey/activity payloads are viewable in dashboard + CSV export from the Submissions tab. Fix: use an **Activity task with your own task_url** (external survey integration): Terac appends `teracSubmissionId`, `submissionId`, `taskId` (or `{TERAC_SUBMISSION_ID}` placeholder); you own the ratings data; redirect back to `https://terac.com/api/external/callback?teracSubmissionId=...&result=completed`. Un-called-back submissions auto-reject after 6h. https://terac.com/docs/researchers/integrations/external-surveys , https://terac.com/api/external/v2/openapi.json
4. **You pay only on approval, and approval is manual by default.** review_type enum: auto_approve | manual_review | self_report. Set `auto_approve` for speed, or your agent must call approve_submission. Credits deducted on approval; "Credits do not top up on their own." https://terac.com/docs/researchers/results/submissions , https://terac.com/docs/researchers/finance/credits
5. **API is v2 beta** ("endpoints and request/response shapes may change"). Rate limit 100 req/min per key -> 429 RATE_LIMITED. https://terac.com/docs/developers/guides/authentication

## 1. API / MCP surface

- MCP endpoint: `https://terac.com/api/mcp` (streamable HTTP). Claude Code: `claude mcp add --transport http terac https://terac.com/api/mcp` then `/mcp` to auth. Cursor/VS Code/Claude Desktop/ChatGPT one-click; other clients via `mcp-remote`. https://terac.com/mcp , https://terac.com/docs/researchers/mcp/install
- Auth: OAuth on first connect, OR API key (`tk_...`, Settings -> API Keys; org-scoped) for headless/CI. REST: `Authorization: Bearer tk_...`, base `https://terac.com/api/external/v2`. https://terac.com/docs/developers/guides/authentication
- MCP tools (22): terac_get_context; terac_list/create/get/update_project; terac_list_filters, terac_get_filter_options; terac_request_feasibility, terac_get_feasibility_request, terac_list_feasibility_requests; terac_create_opportunity, terac_update_opportunity, terac_launch_draft_opportunity, terac_delete_opportunity; terac_list/get/pause/resume/stop_opportunity; terac_get_submissions, terac_get_submission, terac_approve_submission, terac_reject_submission. https://terac.com/docs/researchers/mcp
- REST endpoints mirror those: GET /organization/context; POST/GET /feasibility/requests[/{id}]; /projects CRUD; POST /opportunities, GET/PATCH/DELETE /opportunities/{id}, POST .../launch|pause|resume|stop; GET /opportunities/{id}/submissions, GET /submissions/{id}, POST /submissions/{id}/approve|reject; filters + webhooks (/hooks/event-types). https://terac.com/docs/developers/reference
- CreateOpportunity body (from OpenAPI): required `title, project_id, num_participants (1-1000), business_type ("b2c"|"b2b"), tasks[]`; optional `description (<=8000), filters[{key,value}], unrestricted_audience (bool; almost certainly the "General Population" switch, UNVERIFIED wording), screening_questions (pick types one|any|boolean|text|grid; qualify may|must|must_one_of|reject|review), quotas, cross_quotas, device_types, expected_days_to_complete, feasibility_request_id`. Task item: `sequence, task_type ("interview"|"file_upload"|"activity"), review_type, task_url (URI), title, description, duration_minutes`. Response carries `pricing {cost_per_participant_cents, total_cost_cents, currency}`. No per-task incentive field in the API; incentive set via dashboard/quote.
- Question types: Dashboard survey builder = "structured questions answered in the app ... various question formats" (no enumerated list found; rating/ranking/pairwise UNVERIFIED as native types). Task blocks: Survey, File Upload, Interview (AI voice), Activity (in-app or external URL), Schedule a Call, Agreement. Image/URL stimulus: via Activity/external URL, definitely; native survey media UNVERIFIED. https://terac.com/docs/researchers/opportunities/tasks
- Targeting: filters catalog (demographics, geography, profession, participation history) + screening + quotas; MCP page says both general populations and experts. Respondents: `num_participants` 1-1000.
- Results: poll `GET /opportunities/{id}/submissions` (statuses screen_passed, screened_out, in_progress, awaiting_review, approved, rejected, abandoned) or webhooks `submission.status.change` / `submission.approved` (payload: event_type, event_id, resource_id, occurred_at, opportunity_id, from, to; 12 retries over ~2.5 days; X-Event-ID dedupe). https://terac.com/docs/developers/guides/webhooks

## 2. Latency
See pitfall 2. Documented: first completes in days, standard fill ~1 week; marketing: same-day, median <24h. Pricing step ~1h human. Hackathon-specific latency notes: NOT FOUND online (UNVERIFIED).

## 3. Cost / credits
- Credits-based, bought via Stripe on Finance page; per-participant payout + platform fee (fee % not published); "pay only on approved work"; example CPI shown on /mcp page: ~$28 for a senior engineer PR review. Expert profile rates $24-$220/hr on marketing pages. Genpop per-response price: NOT PUBLISHED (UNVERIFIED; expect quote).
- Precedent: UC Berkeley AI Hackathon 2026 Terac track gave $250 credit per team for human-labeled data. https://ai-hackathon-2026.devpost.com/
- `terac.com/r/...` links: only documented meaning found is the expert-side referral link (activated from a job listing, referral bonus if referee approved). Whether the hackathon `/r/` link grants org credits: UNVERIFIED (not on any public page).

## 4. Agent-callable without a human?
Yes: pure REST/MCP with API key works headless ("CI/headless setups"), idempotent launches for pipelines. Human steps remaining: (a) org signup + credits, (b) Terac-side human pricing on feasibility (~1h), (c) approval unless review_type=auto_approve. Rate limit 100 req/min/key.

## 5. Thesis / positioning
- "Terac is the expert labor MCP", "the supply layer for human labor in a world where AIs run companies", "AI will do most of the world's work with the help of humans"; "the default API call for any AI system that needs to source, hire, verify, or pay a human"; "labor marketplace for the post-AGI future". Founders Zac Baker (CEO), Jack Blair (CTO); $9M from Emergence, SignalFire, Audacious, SV Angel, Z Fellows; ~10 people. https://terac.com/about , https://terac.com/careers
- Network size: 160,000+ registered experts (site), 100k+ elsewhere; "180k+" NOT found on public pages (UNVERIFIED, may be live pitch number). Domain counts: 8k software, 7.5k education, 3k SMB owners, 200+ domains, 195 countries. https://terac.com/ai , https://terac.com/user-research
- Expert vs general population: marketing is expert-first; MCP docs and filters cover "common consumer" audiences too; feasibility page splits "common consumer and standard professional" (fast) vs "niche/custom" (slow).

## 6. Existing "agents hire humans for judgment" examples on Terac
- Only first-party: /mcp use cases (PR review for race conditions, research, judgment calls, RLHF/reward modeling, customer interviews) and the Berkeley annotation track. No third-party GitHub repos/blogs found (UNVERIFIED that none exist; 25-min search). Closest tutorials are RentAHuman's MCP tutorial. https://terac.com/mcp , https://rentahuman.co/blog/building-mcp-tools-that-hire-humans

## Competitor check (one line each)
- getabrain.ai: UNVERIFIED. Nearest hit is getbrain.ai (sales AI, voice/video clones), unrelated. https://www.instagram.com/getbrain.ai/
- verifi: UNVERIFIED as named. Related: verifiedbyhumans.org (credentialed experts certify AI outputs), verifiedagent.ai "Veri" (agent benchmarks/rental). https://verifiedbyhumans.org/
- meatspace: EXISTS, meatspace.so "AI Agents Hire Humans"; sibling of RentAHuman.ai (Alexander Liteplo) which lets agents book/pay humans for physical tasks via MCP/REST. https://www.meatspace.so/ , https://rentahuman.ai/
- humanrelay: UNVERIFIED as a product; "human relay" is a pattern (Tryb blog, Kilo AI provider). HumanLayer (YC F24) is the real API for agent->human approvals over Slack/email. https://tryb.dev/blog/human-in-the-loop-for-ai-agents
- pausepoint: UNVERIFIED. Similar: Cheqpoint (human approval for AI assistants), Restate HITL pattern. https://www.cheqpoint.co/
- humanrail: EXISTS, humanrail.dev, "Human Escalation Layer for AI Agents": routes to vetted human, 6-stage QA, pays via Lightning, one API call. https://humanrail.dev/
- ClawHub askhuman: EXISTS in awesome-openclaw-skills, "Human Judgment as a Service for AI agents". https://github.com/VoltAgent/awesome-openclaw-skills
- ask-a-human: UNVERIFIED (not found).
- loopuman: UNVERIFIED (not found).
- sanctifai: EXISTS (SanctifAI): agents task humans for verification, escalation, consultation, simulation; marketplace with MCP/API, on-chain attestations. https://hatchworks.com/talking-ai/ai-agents-could-hire-you/
- magic api: EXISTS as OpenClaw skill: routes agent tasks to human executive assistants (Magic). https://playbooks.com/skills/openclaw/skills/magic-api
- agentdo: UNVERIFIED (not found).

## Sources
https://terac.com/mcp | https://terac.com/docs/researchers/mcp | https://terac.com/docs/researchers/mcp/install | https://terac.com/docs/developers | https://terac.com/docs/developers/reference | https://terac.com/docs/developers/guides/authentication | https://terac.com/docs/developers/guides/webhooks | https://terac.com/api/external/v2/openapi.json | https://terac.com/docs/researchers/opportunities/tasks | https://terac.com/docs/researchers/opportunities/creating-an-opportunity | https://terac.com/docs/researchers/recruitment/feasibility | https://terac.com/docs/researchers/results/submissions | https://terac.com/docs/researchers/integrations/external-surveys | https://terac.com/docs/researchers/finance/pricing | https://terac.com/docs/researchers/finance/credits | https://terac.com/about | https://terac.com/ai | https://terac.com/user-research | https://terac.com/platform | https://ai-hackathon-2026.devpost.com/
