---
type: reference
status: active
created: 2026-08-15
sources: Granola transcript "Zero Human Hackathon" 2026-08-15 09:29 (opening statements), "[GUIDEBOOK] - Zero Human Company Hackathon by Terac" (Notion PDF, 37 pages), docs/research/kickoff-notes.md
---
# Hackathon rubric: Zero Human Company Hackathon by Terac, 2026-08-15

What this hackathon rewards, as binary claims a model (and a stranger) can judge from a team's repo,
slides, and landing page. The one fenced JSON block below is the machine-readable rubric; the prose
is context for humans. Ids are stable and become finding ids in the report.

## What the room actually said (context)
- Theme, verbatim from the organizer: "build an agent that can run the entire company autonomously":
  building the product, marketing and outbounds, selling, payments, legal/compliance, hard decisions.
- Two hard rules for ALL projects: use the Terac MCP (real human input collected during the hackathon
  that makes the project measurably better, clear before/after, general-population studies), and take
  payments through an individual Stripe account (organizers track who "walked out with the most revenue").
- Compete in as many tracks as you want; more tracks = better odds.
- Prizes: Best Overall ($2,500: creativity, technical skill, impressiveness), Best Agent-Run Company
  ($2,500: real revenue today + viable company in 5-10 years), Linq ($1,500/$1,000), Replay ($1,000/$500),
  Superserve ($1,000/$500), Pioneer ($500, Fastino models bonus), Band ($500, "remove Band and it breaks"),
  Render ($500/$300/$100 credits, must use Render Workflows).
- Judges: YC S26 founders (Touchmark, Olam Labs, Egoist Machines, Brekfuz), Stripe Head of Advanced AI,
  a DeepMind group PM, an ex-xAI engineer, a CRED growth lead. Read: they will judge product craft,
  revenue mechanics, and whether the autonomy is real, not slideware.
- Terac's own frame: "one day agents will run entire enterprises... that is not the case yet"; the
  human in the loop is the point, not a concession.
- Submissions lock 18:30 (guidebook says 6:45; the stage said 6:30: treat 18:30 as the deadline).

## Rubric (parsed by the code session; everything outside this block is prose)
```json
{
  "hackathon": "Zero Human Company Hackathon by Terac, 2026-08-15, Humanmade SF",
  "judging": [
    {
      "id": "judge/autonomy",
      "title": "An agent runs the company, end to end",
      "weight": 3,
      "claims": [
        "The project names which company functions agents perform (at least three of: build product, market/outbound, sell, take payments, legal/compliance, hard decisions)",
        "At least one business decision in the project is made by an agent without a human approving it, and the pitch shows where",
        "The pitch states explicitly where a human is still in the loop and why an agent cannot do that step yet",
        "The product exists and a stranger could use it today, not only in a demo video"
      ]
    },
    {
      "id": "judge/terac-human-loop",
      "title": "Terac human loop, the required rule and the host's own bar (fails = not a contender)",
      "weight": 4,
      "claims": [
        "The project calls the Terac MCP or API to recruit real people during the hackathon",
        "The people respond to something concrete (use, rate, rank, label, compare, or judge an artifact), not a general survey",
        "The pitch shows a before and after: what changed because of the human input, with a number",
        "The study targets the general population (or says why an expert panel was necessary)",
        "What the humans receive is concrete and short: a specific artifact plus a few yes/no questions they can answer in minutes"
      ]
    },
    {
      "id": "judge/revenue",
      "title": "Real revenue today through Stripe (required for Best Agent-Run Company)",
      "weight": 3,
      "claims": [
        "There is a Stripe payment link or checkout a stranger can pay through right now",
        "A price is stated in dollars",
        "The pitch reports revenue earned during the hackathon (a number, even if small)",
        "A stranger can go from landing page to paid in under a minute without talking to the team",
        "The pitch names the Stripe individual account and the revenue number the organizers will use to rank 'who walked out with the most revenue'"
      ]
    },
    {
      "id": "judge/viability",
      "title": "Viable company in 5-10 years",
      "weight": 2,
      "claims": [
        "The pitch names who pays and why they pay again (recurring or repeatable)",
        "The pitch says what the business looks like at scale, not just today's demo",
        "The pitch names the reason this business exists specifically because agents got cheap (why now)",
        "The pitch names a real competitor or current workaround and why this wins"
      ]
    },
    {
      "id": "judge/impressiveness",
      "title": "Creativity and technical skill (Best Overall)",
      "weight": 2,
      "claims": [
        "The core mechanism is novel, not a chat wrapper around a model with a payment button",
        "The demo shows the system working live end to end (input to money or output), not slides describing it",
        "The one-line pitch is stated in the first screen of the deck or the top of the landing page",
        "The technical architecture is drawn or described well enough that an engineer judge can see the hard part"
      ]
    },
    {
      "id": "judge/tracks",
      "title": "Enters as many tracks as it honestly qualifies for",
      "weight": 1,
      "claims": [
        "The submission names which tracks it competes in",
        "For each named sponsor track, the pitch states how the sponsor product is used and where it is in the stack",
        "The repo is public with a README that says how to run it, and the demo link works",
        "The submission includes the Stripe account info the organizers asked for (individual account, payment link, read-only key)",
        "The pitch shows sponsor products combined so they make each other better (the organizer's stated reason for multi-track entry), not bolted on"
      ]
    }
  ],
  "sponsors": [
    {
      "id": "sponsor/terac",
      "name": "Terac (host, required)",
      "required": true,
      "claims": [
        "The project uses the Terac MCP or API to hire real people during the hackathon",
        "The human task is one an agent could not do or should not decide alone (judgment, taste, physical world, verification)",
        "The output of the humans changes the product or the verdict, and the pitch shows the delta",
        "The human task is one of the kinds Terac named on stage: a physical-world task, a computer-use task an agent cannot do, an engineer getting an agent unstuck, or expert judgment",
        "The pitch reports how many people responded and how fast (Terac's pitch is minutes, not hours)"
      ],
      "evidence_hints": [
        "terac",
        "app.terac",
        "TERAC_API_KEY",
        "terac_create_opportunity",
        "MCP",
        "human in the loop"
      ]
    },
    {
      "id": "sponsor/stripe",
      "name": "Stripe (required for payments)",
      "required": true,
      "claims": [
        "Payments run through Stripe (payment link, checkout, or Agent Pay)",
        "The Stripe account is an individual account created for this hackathon and its info was submitted",
        "The pitch mentions Stripe Atlas or incorporation as the path beyond the hackathon (bonus, not required)"
      ],
      "evidence_hints": [
        "stripe",
        "buy.stripe.com",
        "checkout.stripe.com",
        "STRIPE_",
        "payment link",
        "client_reference_id"
      ]
    },
    {
      "id": "sponsor/linq",
      "name": "Linq (iMessage/RCS/SMS API), $1,500 / $1,000",
      "required": false,
      "claims": [
        "The agent sends or receives iMessage, RCS, or SMS through Linq with a real phone number",
        "The text channel is where a customer or a human-in-the-loop actually acts (buys, votes, replies), not a notification only",
        "It uses a rich iMessage feature (tapbacks, reactions, iMessage Apps card, Agent Pay checkout, group chat)",
        "The text thread is multiplayer where it helps (a group chat where customers debate a purchase together, as Linq suggested on stage)",
        "Checkout happens in the thread via Agent Pay / Stripe, money settling to the team's Stripe"
      ],
      "evidence_hints": [
        "linq",
        "linqapp",
        "LINQ_API_KEY",
        "@linqapp/sdk",
        "iMessage",
        "api/partner/v3",
        "webhook-subscriptions"
      ]
    },
    {
      "id": "sponsor/replay",
      "name": "Replay QA, $1,000 / $500",
      "required": false,
      "claims": [
        "The team ran Replay QA against its own web app during the hackathon",
        "Bugs Replay found were fixed and the pitch shows a clean or improved report",
        "Replay is used programmatically (API or MCP) as part of the product or the build loop, not one manual run",
        "Replay bug reports were pasted back into the team's coding agent to fix (the loop Replay's CEO demoed on stage)",
        "Continuous QA is connected to the GitHub repo or deploy, so each push is re-tested"
      ],
      "evidence_hints": [
        "replay",
        "qa.replay.io",
        "loop-qa.replay.io",
        "REPLAY_API_KEY",
        "lqa_",
        "bug report"
      ]
    },
    {
      "id": "sponsor/superserve",
      "name": "Superserve sandboxes, $1,000 / $500",
      "required": false,
      "claims": [
        "Agents execute code, browse, or manage files inside Superserve sandboxes as a core part of the stack",
        "The project pauses and resumes sandbox state between agent turns",
        "Removing Superserve would break the project, not just slow it",
        "The pitch says what runs in the sandbox that would be unsafe or impossible on the app server"
      ],
      "evidence_hints": [
        "superserve",
        "docs.superserve.ai",
        "SUPERSERVE_API_KEY",
        "Sandbox.create",
        "sandbox0"
      ]
    },
    {
      "id": "sponsor/pioneer",
      "name": "Pioneer by Fastino Labs (open-weight models), $500",
      "required": false,
      "claims": [
        "The product runs on open-weight models served through Pioneer",
        "It uses a Fastino model (GLiNER2, GLiGuard, GLiNER2-PII) or fine-tunes an open model with the Pioneer API",
        "The pitch says why an open model was the right choice here (cost, privacy, control)"
      ],
      "evidence_hints": [
        "pioneer",
        "fastino",
        "GLiNER",
        "GLiGuard",
        "docs.pioneer.ai",
        "qwen",
        "gemma",
        "llama"
      ]
    },
    {
      "id": "sponsor/band",
      "name": "Band (agent-to-agent coordination), $500",
      "required": false,
      "claims": [
        "Agents coordinate through a Band chat room using @mentions, and removing the room breaks the project",
        "There is at least one real dependency: a handoff that changes an answer, a specialist added at runtime, an enforced boundary between accounts, or a verdict one agent can block",
        "The submission states the one-line flow and who talks to whom",
        "Agents on Band are discoverable through the registry and use consent (contacts) before using each other's agents",
        "The pitch says what breaks when the Band room is removed"
      ],
      "evidence_hints": [
        "band",
        "band.ai",
        "band-sdk",
        "@band-ai/sdk",
        "band_send_message",
        "band_lookup_peers",
        "chatroom"
      ]
    },
    {
      "id": "sponsor/render",
      "name": "Render (hosting; Workflows required for the track), $500 / $300 / $100 credits",
      "required": false,
      "claims": [
        "The project is deployed on Render and the live URL works",
        "The project uses Render Workflows for a long-running or multi-step task (required to qualify)",
        "The deploy is reproducible (render.yaml or documented service settings)"
      ],
      "evidence_hints": [
        "render",
        "onrender.com",
        "render.yaml",
        "Render Workflows",
        "RENDER_API_KEY"
      ]
    },
    {
      "id": "sponsor/lovable",
      "name": "Lovable (credits, no track)",
      "required": false,
      "claims": [
        "The customer-facing surface was built with Lovable and is live",
        "The Lovable front end talks to the team's own backend or payment link (not a static mock)"
      ],
      "evidence_hints": [
        "lovable",
        "lovable.app",
        "lovable.dev"
      ]
    },
    {
      "id": "sponsor/whop",
      "name": "Whop (partner, no track)",
      "required": false,
      "claims": [
        "The project uses Whop to run or sell part of the business (checkout, memberships, payouts)"
      ],
      "evidence_hints": [
        "whop",
        "api.whop.com"
      ]
    }
  ],
  "messaging": [
    {
      "id": "msg/thesis",
      "theme": "Answers the hackathon's question: can a business run autonomously?",
      "claims": [
        "The pitch says in one sentence what part of a company the agents run without people",
        "The pitch says in one sentence what people still do and frames that as a design choice, not a gap",
        "The pitch connects to the organizer's theme (agents running a company end to end) in the first minute or first screen"
      ]
    },
    {
      "id": "msg/first-screen",
      "theme": "A stranger gets it in ten seconds",
      "claims": [
        "The first screen of the deck or top of the landing page states what it is, for whom, and what it costs",
        "The headline names a problem the judge already recognizes",
        "There is one obvious call to action (buy, try, text the number) above the fold"
      ]
    },
    {
      "id": "msg/proof",
      "theme": "Shows receipts, not adjectives",
      "claims": [
        "The pitch shows a revenue number from today, even if small",
        "The pitch shows how many real people responded via Terac and what changed because of them",
        "The pitch shows the product working live or a recording of it working end to end"
      ]
    },
    {
      "id": "msg/tracks",
      "theme": "Tells the judges which prizes it is competing for and why it qualifies",
      "claims": [
        "The deck names the tracks entered",
        "For each sponsor track named, the deck says where that sponsor product sits in the stack in one line",
        "The deck does not claim a sponsor it does not actually use"
      ]
    },
    {
      "id": "msg/judge-fit",
      "theme": "Speaks to this panel: YC founders, Stripe Head of AI, a DeepMind PM, growth leads",
      "claims": [
        "The pitch shows the payment flow and unit economics, not only the AI",
        "The pitch shows product craft (a real UI or channel a customer touches), not only an architecture diagram",
        "The pitch says what the team would do on Monday if it won"
      ]
    }
  ],
  "technical": [
    {
      "id": "tech/runnable",
      "title": "A stranger can run and deploy it",
      "claims": [
        "The README says how to install and run the project in a few commands",
        "Configuration is by environment variables with an example file, and no secret is committed",
        "There is a deploy config or documented deploy steps that produce the live URL",
        "There is at least one automated test or health check"
      ]
    },
    {
      "id": "tech/vibe-to-mvp",
      "title": "From vibe-coded hackathon project to an MVP you can hand users",
      "claims": [
        "State that matters (users, orders, results) is persisted somewhere that survives a redeploy",
        "Errors are handled: a failed external call (model, payment, API) produces a clear message, not a crash",
        "There is a way to know it broke in production (logs, health endpoint, alerts)",
        "Payments and secrets are handled server-side, not in client code",
        "The product has one clear user path from arrival to value with no dead ends"
      ]
    },
    {
      "id": "tech/marketable",
      "title": "Ready to put in front of users and market",
      "claims": [
        "There is a public URL a user can visit without a login wall or an invite",
        "The site is findable and trustworthy at a basic level (title, description, privacy and terms pages, contact)",
        "The pitch names the first channel the team would use to get users and why those users are reachable"
      ]
    }
  ],
  "human_panel": {
    "note": "What the humans receive (Aria, 14:20): an agentic panel runs first, then a small human panel from different domains judges on top of it. Humans get a one-page brief, never the raw repo.",
    "brief": [
      "one-line pitch as the team wrote it",
      "the first screen of the deck or landing page (image or text)",
      "the agentic panel's one-line verdict per gap (shown only after the blind vote, per #5)",
      "3 yes/no questions + one free-text: 'in one line, what does this company do and who pays?'"
    ],
    "domains": [
      {
        "id": "human/customer",
        "who": "a plausible buyer from the general population",
        "asks": "would you pay, what would stop you"
      },
      {
        "id": "human/founder",
        "who": "someone who has shipped a product",
        "asks": "is this a business or a demo, what is missing to charge"
      },
      {
        "id": "human/engineer",
        "who": "an engineer",
        "asks": "does the autonomy claim hold, where is the human really"
      }
    ],
    "agentic_panel": [
      {
        "id": "agent/judge",
        "persona": "a hackathon judge from this panel (YC founder / Stripe AI lead / DeepMind PM)"
      },
      {
        "id": "agent/sponsor",
        "persona": "a sponsor rep checking meaningful use of their product"
      },
      {
        "id": "agent/investor",
        "persona": "a seed investor asking who pays and why now"
      },
      {
        "id": "agent/customer",
        "persona": "a stranger deciding whether to pay in the next minute"
      },
      {
        "id": "agent/engineer",
        "persona": "an engineer reviewing the repo for vibe-coded fragility"
      }
    ]
  },
  "terac_first": {
    "note": "Aria 15:00: focus on Terac more than anything. Terac is host, the required rule, and its network IS our human layer. Every Reality Check job launches a Terac general-population study (n=3, auto_approve, activity task pointing at our /rate page so we own the answers). The report's Terac row is first and itemized. Our own submission must show a before/after number from Terac respondents.",
    "our_own_study": {
      "launch": "now, on our own landing page + pitch, general population, n=5, auto_approve",
      "measure": "share who can say what we do + share who would pay, before and after we rewrite the hero from their answers",
      "show": "slide with before/after numbers and two quotes"
    },
    "human_steps": [
      "redeem the $100 Terac hackathon credit from the Notion guidebook (balance was $25)",
      "ask Jack (Terac cofounder, on the floor): cheapest role for 'read a page, answer 3 yes/no', realistic ETA today, whether $100 buys 5+ responses"
    ]
  }
}
```

## How the report should read it (for #4)
- Hackathon section first: "How to win this hackathon". Judging items sorted by weight; each failed claim
  becomes a fix with an owner. Sponsors: list which tracks the project honestly qualifies for, which it
  claims but does not evidence, and the cheapest sponsor it could add before 18:30. Messaging: rewrite
  suggestions with the exact slide or screen to change.
- Business gaps second (payer / take_money / stranger_proof / loop) from `docs/specs/agent-report.md`.
- If a GitHub repo was supplied: `technical` items render as "what it would take to hand this to users",
  qualitative advice, no probes required.
- Every claim is judged from README + slides + page text; when the text is silent the finding says
  "not evidenced: say it if it is true" (that is itself the fix).
