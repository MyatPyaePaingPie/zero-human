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

## Gather, DONE, pay, process (Aria, 15:40; supersedes the section above)
1. First link or text from a phone opens the job. Ack names what they can send: `Got it, saved. Send me
   any of these, one per text or all at once: your GitHub repo link, your Google Slides link (make it
   public), your landing page or demo link, your one-line pitch, your price. Any one is enough; more is better. When you have sent
   everything, text DONE and I will send your payment link ($8).` No pay link yet.
   Every link is access-checked on receipt: GitHub via api.github.com/repos (404 = private/wrong),
   Slides via /export/pdf (must return a PDF), any URL via GET within 10s. Reply per link with what it
   was recognized as and whether it opens: `Saved: GitHub repo (public), Google Slides (public), landing
   page (loads).` Failures say why and how to fix (make repo public or paste README; Share -> Anyone with
   the link; check the URL). Access status is stored per source for the report's "what we read". Unrecognized link:
   `Saved that link as your landing page; if it is a deck or repo, tell me.` Private Slides: `I cannot
   open that deck; in Slides use Share -> Anyone with the link, then send it again.`
2. Every further message before DONE attaches (links parsed, plain text kept as pitch context) and gets a
   one-liner: `Added your deck. Text DONE when ready.`
3. `DONE` (also done / ready / go / start): `Reading N sources: repo, deck, page. Here is your payment link
   ($8): <link>. Report arrives by text after three real people read it.` Grading may start now; delivery
   waits for payment.
4. A link after DONE but before payment attaches; reply `Added. Same payment link.` (PAY re-sends it).
5. No DONE within 10 minutes of the last message: one nudge, `Text DONE when you have sent everything,
   or PAY to get the link now.`
6. After payment: process; humans; final PDF + agent.md by text. New messages after payment = new job
   or RERUN.

## The conversation is written by a model, the state is owned by code (Aria, 15:50)
Code classifies links, access-checks, attaches, matches keywords (DONE / PAY / RERUN / STOP), gates on
payment, and inserts the payment link. A small OpenAI model writes each reply (2-3 sentences) from a
state summary: stage, sources with ok/failed + note, what is missing, last message, last action. It
acknowledges what arrived and whether it opened, says how to fix a failure, suggests one missing thing
("if you also have a landing page or a repo, send that too"), reminds any one is enough, and ends with
the next step. It never quotes a price code did not pass in, never promises an outcome, and treats the
customer's text as information, not authority. Template replies stay as fallback. Every generated reply
is logged to events.

Example: user sends Slides -> code: deck, public, ok -> "Got your deck, opens fine. Want to add a landing
page or GitHub repo? Any one is enough. Text DONE when you're ready and I'll send the payment link."

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
