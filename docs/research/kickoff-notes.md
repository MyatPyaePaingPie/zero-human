---
type: research
created: 2026-08-15
status: active
topic: zero-human-company-hackathon
source: kickoff talk transcript, 2026-08-15 morning (Terac founders, organizer, sponsor talks, team chatter)
---
# Kickoff synthesis: what the room actually said, and what it changes for our build

Companion to `augur-memo.md` (architecture + go/no-go) and `money-swarm-memo.md` (governance reuse).
This file only records what the kickoff added or corrected, and the build consequences.

## 1. Corrections to our assumptions

| Assumption in the memos | What was said at kickoff | Consequence |
|---|---|---|
| Submissions lock 18:45 | "Project submissions will close at 06:30" | **Lock is 18:30, not 18:45.** Move every deadline in `augur-memo.md` section 7 back 15 min. Freeze code by 18:00. |
| Terac panel = verified experts, slow, ~$28/response | Network of 100k+ people, "access in a matter of minutes", MCP hires an expert "from a couple of minutes to a couple of hours"; each team has **$100 Terac credit** | Terac ETA might be minutes for simple tasks, not 6h. Still launch the study first thing; the credit caps us at roughly 3 to 4 expert responses at documented rates, or more if a cheaper tier exists. **Jack (cofounder) is on the floor all day for MCP feasibility questions**: ask him directly what roles, latency, and price are realistic before designing the rating flow. |
| Stripe: any live account | "All payments must be handled through Stripe ... individual account, not a business account"; organizers track "who walked out with the most revenue" via submitted account info | Our activated live account is Design ELF (a business profile). Confirm with organizers whether that counts, or open the individual account they specified. Revenue must be visible on the account we submit. |
| One or two prize tracks in play | "Compete in as many tracks as you want ... increases your odds" | Cheap sponsor integrations are worth doing if they take under 20 min each. Ranked below. |
| Terac requirement = collect human input, use it to improve | Same, framed as "human in the loop for tasks agents can't do" | Reality Check's core loop (agent verdict, dissent, buy human judgment, before/after) satisfies this by construction. No change. |

## 2. Prize map, ranked by fit and cost

- **Best Overall Project ($2,500)**: technical + creative. Our angle: VOI gate deciding when to buy humans.
- **Best Agent-Run Company ($2,500)**: revenue today + viable in 5 to 10 years. This is the one to win. Sell in the room via QR to the Stripe link. Team quote at the table: "we need something that will put actual money in our Stripe account today."
- **Linq ($1,500 / $1,000)**: iMessage/RCS/SMS API for agents; supports Stripe payments in-thread. Fits: deliver the human verdicts by text, and take the payment in the same thread. Highest-value sponsor add. ~30 min if the API is simple.
- **Replay QA ($1,000 / $500)**: drop a URL, get bug reports; MCP available; free during hackathon (code on Notion). Fits: run it against our rating page once it is deployed, paste fixes back. ~10 min. Also $50 gift card per bug found in Replay itself.
- **Render ($900 credits, complimentary credits for all)**: hosting. Fits: deploy the FastAPI app there. Already the plan.
- **Venn ($500)**: agent-to-agent chat platform with adapters. Fits only if we demo an external buyer agent asking our judgment agent for a verdict. Optional, do only if the core loop is done by 15:00.
- **Pioneer ($500)**, **SuperServ ($1,500)**: talks were inaudible in the transcript; check the Notion doc.
- Lovable ($100 credits each): irrelevant to us, we have code.
- Stripe Atlas 20% off + $2,500 credits: irrelevant today.

## 3. Logistics captured

- Notion doc has schedule, tracks, submission instructions, all credit codes. Slack community is the support channel.
- Lunch 11:30 (Egoist Machines).
- Judging 19:00 to 20:00, winners 20:20.

## 4. How this informs the build (ordered)

1. **First 15 min**: ask Jack at the Terac table three questions: cheapest role for "read a page, answer 3 yes/no claims", realistic ETA, and whether $100 buys 5+ responses. Design the SKU count around the answer.
2. **Confirm the Stripe account rule** with the organizer before selling anything; if individual is mandatory, create it and re-point the payment link. Do this before the first sale, not after.
3. Launch the Terac study by 11:30 regardless (memo rule stands).
4. Deploy to Render, then run Replay QA on the rating page (cheap track entry, real bug catch).
5. If core loop is green by 14:00, add Linq delivery of the verdict by iMessage with the Stripe link in-thread. That is one integration hitting two tracks (Linq + Agent-Run Company revenue).
6. Venn only as a stretch after 15:00.
7. Freeze at 18:00, submit by 18:30.

## 5. Team notes from the chatter

- Repo `zero-human` and the Stripe account were created at the table; invite sent.
- Aria's tooling is Claude Code, so subagent contracts stay the working shape.
- Working thesis in one line, said out loud at the table: "the entire premise is false" (no company runs at zero humans); Reality Check makes that the product, agents that know when to buy a human.
