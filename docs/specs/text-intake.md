---
type: spec
status: active
created: 2026-08-15
issues: [20, 6, 18]
---
# Text the number: the whole product in one thread

Aria, 16:30: no website, no form. Text our Linq line, tell it what you built, get the result.
The website stays only as the place the PDF and agent.md are hosted (and the pay link for later).

## The conversation
1. **Human texts** the line (+1 415 577 0605) anything: links, or "hey I built X".
   Linq is inbound-first, so this is also the opt-in. Existing `handle_inbound` receives it.
2. **We parse links** from the message: `github.com/...` = repo, `docs.google.com/presentation` = slides,
   any other http(s) = landing page. Any subset. If none: reply
   `Send me a link to your repo, your slides, or your landing page. Any one works, all three is best.`
3. **Ack immediately** (no link in the first outbound: Linq sandbox rule):
   `Got it. Reading your repo and page now. Grading it against today's rubric and the sponsor tracks. Give me about two minutes.`
   Show a typing indicator while the job runs (Linq: typing indicator = loading state).
4. **Result text** when the report renders (links allowed from the second message on):
   ```
   <Project>: Hackathon FIXABLE BY 18:30 · Autonomous 2/7 · Business NOT YET
   Do first: 1) <fix> 2) <fix> 3) <fix>
   Sponsor tracks you qualify for: Terac, Stripe. Cheapest to add: Replay.
   Full report (PDF): <url>   For your coding agent: <url>/agent.md
   Reply RERUN after you fix things. Reply HUMANS to hear what 3 strangers said when it lands.
   ```
5. **Humans land** (Terac, async): a follow-up text:
   `3 strangers read your pitch: 2 of 3 could say what it does, 1 of 3 would pay. "I thought it was for developers." Knowing it is AI-run: 2 less willing, 1 same. Rewrite the headline; details in the PDF.`
6. **Replies:** `RERUN` re-fetches the same links and sends the delta (`fixed: 4, regressed: 0, new stamp ...`).
   A tapback on the result message = "send me agent.md again" (Linq: tapback as a vote/action). Optional.
   `STOP` opts out (exists).

## One job per phone until payment (Aria, 15:35)
Everything a phone sends before it pays attaches to its open job: more links, a plain-text pitch, a
price. The ack invites it: `Got it. Reading your repo, deck, and page now. Feel free to text more before
you pay: another link, your one-line pitch, your price. Next text is your payment link ($8); the report
comes right after.` Extra messages get a one-liner (`Added your deck.`), never a second pay link (PAY
re-sends it). A single message with several links is parsed whole. After payment, new messages start a
new job or RERUN.

## What this replaces
- The Lovable form is no longer the intake. Keep the storefront page only as landing + hosting for
  the report URLs and the payment link. keydriver: one line "Text +1 415 577 0605 with your repo,
  slides, or landing page" replaces the form.
- Payment: free for the room today via text. Paid path stays on the website for after.

## Constraints (from Linq sandbox rules, docs/research/sponsor-findings.md)
- Inbound-first: we never cold-text. First outbound message: no links, no effects, no reply_to.
- Sandbox: 100 contacts, number valid 7 days. Fine for today; note it in the deck.
- Webhook signature verification exists (`verify_signature`).

## Build (code session, in this order)
1. Extend `handle_inbound`: link parse -> create job via the #20 sources path -> ack text.
2. On report render: send result text (step 4). Reuse `notify_verdict` shape.
3. On Terac settle: send humans text (step 5).
4. `RERUN` keyword: new job with same links + `before_job` link for the delta.
Estimate: 45-60 min on top of #20/#4. Do after the PDF renders once; the text is only worth sending
when the thing it links to exists.

## Why this also wins Linq
Their bar, verbatim from the guidebook: primitives as UI (typing = loading, tapback = action), vertical-
specific, not a generic bot, and the richest possible experience in the thread. This is exactly that:
the thread IS the product for hackathon teams, and the human panel arrives in the same thread.
