---
type: spec
status: active
created: 2026-08-15
issues: [4, 18]
---
# The human task: what Terac people see, what we ask, what comes back

Three strangers from Terac's general-population network per job. Blind: they never see the model's
verdict. About three minutes. Delivered as a Terac activity task whose `task_url` is our
`/rate/{job}` page (we own the answers; on submit we redirect to Terac's completion callback).

Design rule: ask only what a stranger can answer better than a model. Comprehension, willingness to
pay, trust, price sense, and the hackathon's own question (would you buy from a company run by AI).
Never ask them to judge code, architecture, or "is this a good idea".

## 1. Terac opportunity (what the recruiter sees)
- Title: `Read a startup's pitch and answer 5 quick questions (3 minutes)`
- Description: `You will read how a new company describes itself (its headline, first screen, and a short pitch) and tell us honestly what you understood, whether you would pay, and what you would change. No right answers. No web searching. About 3 minutes.`
- Audience: general population, `unrestricted_audience: true`, n=3 per job, `review_type: auto_approve`.
- Screener (one question, must-pass): `Have you bought anything online in the last 30 days?` yes.
- Task: activity, `task_url = {RC_PUBLIC_BASE}/rate/{job}?teracSubmissionId={TERAC_SUBMISSION_ID}`, duration 3 min.

## 2. What they see on /rate/{job} (the brief, one screen)
Header: `Read this like you just stumbled on it. Then answer honestly. We are testing the company, not you.`

Stimulus, in this order, nothing else:
1. The headline and first screen (screenshot of the landing page hero, or the first slide, or the first
   line of the README, whichever exists first in that order).
2. The one-line pitch in the team's own words.
3. The price, if any is stated. If none: `No price is shown.`

No repo, no full deck, no probe results, no model output.

## 3. The five questions (each answered in under 30 seconds)
1. `In one line: what does this company do, and who is it for?` (free text, required)
2. `Would you, or someone you know, pay for this?` yes / no, then `Who, and why or why not?` (one line)
3. `Is the price clear?` yes / no / no price shown. If yes: `fair / too high / too low`.
4. `Would you trust it enough to give it your card today?` yes / no, then `What would make you trust it more?` (one line)
5. `This company is run mostly by AI, with few or no people involved. Knowing that, are you more, less, or equally willing to buy?` more / less / same, then `Why?` (one line)
Optional 6: `If you could change one thing on this page, what would it be?` (one line)

## 4. What comes back (stored per respondent, keyed by job + Terac submission id)
```json
{"job":"j_...","submission_id":"...","seconds":142,
 "q1_what":"a tool that checks your startup idea using real people",
 "q1_match":null,
 "q2_pay":true,"q2_who_why":"a founder friend, before spending on ads",
 "q3_price":"clear","q3_fair":"fair",
 "q4_trust":false,"q4_more":"show who is behind it and a refund line",
 "q5_ai_effect":"less","q5_why":"I want a person to complain to",
 "q6_change":"the headline says nothing about who it is for"}
```
`q1_match` is filled afterwards by one model call comparing `q1_what` to the team's own one-line
pitch (yes / partial / no). That is the comprehension score. Everything else is counted directly.

## 5. How the report uses it
- Page 1 block: `Could say what it does: k of n. Would pay: k of n. Would hand over a card: k of n. Price clear: k of n. Told it is AI-run: more / less / same counts.` plus two verbatim quotes (q1 and q6 first).
- Business gaps: q1/q2 feed `payer` and `stranger_proof`; q3/q4 feed `take_money`.
- Hackathon: q5 is the answer to the organizer's own question and goes on page 1 and in the deck advice ("2 of 3 strangers said AI-run makes them less willing; your page should say where the humans are").
- Autonomy: q5 and q4 feed `auto/human-loop-design` (is the human placed where trust needs it).
- Messaging rewrites quote q1 and q6 verbatim as the brief for the headline fix.

## 6. Our own study (the before/after we show judges)
Run this exact task on our own landing page + pitch (n=5) at the 17:00 launch. Rewrite the hero from
q1/q6 answers. Re-run (n=3). Slide: `Could say what we do: 2 of 5 -> 3 of 3. Would pay: 1 of 5 -> 2 of 3.` plus two quotes.
