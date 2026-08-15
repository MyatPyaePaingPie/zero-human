---
type: spec
status: active
created: 2026-08-15
issues: [4, 18]
sources: terac_get_context, terac_list_filters, terac_get_opportunity on our two drafts (16:15 PDT)
---
# The Terac opportunity, exactly

What the MCP actually does, read live from our org (ZeroHuman, balance $125 after the credit landed),
and the payload we launch per job. Read this before touching `terac_client.py`.

## How Terac works (facts that shape the design)
1. **Three gates before a person sees our page:** hard `filters` (profile, free, instant), our
   `screening_questions` (a form, graded by `qualify_logic`), then **Terac's own AI voice screening
   interview, which runs on every study that has a screener, and a study cannot launch without one.**
   It costs no money; it costs TIME. This is the biggest latency unknown for "minutes, not hours".
   Ask Jack how long that interview stage takes today for a general-population 3-minute task.
2. **Pricing is derived from duration.** 3 minutes -> CPI $6.00 (machine estimate on our draft), so
   n=3 is $18 per job. `terac_request_feasibility` gets a human-confirmed price in ~1 hour; not worth
   it today. Budget: $125 = our own study n=5 ($30) + one re-run n=3 ($18) + ~4 buyer jobs.
3. **`auto_approve` pays automatically only if our page redirects to
   `https://terac.com/api/external/callback?teracSubmissionId=...&result=completed`.** Otherwise it
   silently falls back to manual review and nobody gets paid until we approve. Terac appends
   `submissionId`, `teracSubmissionId`, `taskId` to our `task_url`.
4. **`expected_days_to_complete` minimum is 5 calendar days.** It is a window, not a promise; nothing
   in the dashboard shows it. Set 5.
5. **Filters vs screener:** filters decide who can SEE the study, screener decides who gets IN. A
   single-select screener whose answers are all "may/must" screens nobody out; there must be a
   `reject` answer. Do not reveal the criterion in the question.
6. **`unrestricted_audience: true` recruits worldwide, any age, any language.** Do not use it. Country
   + language + age filters are free and cut junk.
7. `reference--has_not_taken_study` with `$in: [prior opportunity ids]` excludes people who rated a
   previous job: keeps panels independent across runs (the augur lesson, unnamed).
8. `max_responses_per_expert` is 1 by default. `customer_screening_review: auto_invite` is what we want.

## State of our org right now
- Draft `s0ver3mnpjii25t4ix12ot0j` "Quick read: judge a short startup pitch" (code session's calibration
  draft): correct shape (b2c, activity, auto_approve, 3 min, English screener with a reject) but its
  `task_url` points at the OLD host `reality-check.onrender.com`. Fix to `reality-check-qhy9.onrender.com`
  or it will never fire the callback.
- Draft `e5m491hmv1pl30ayncall8lu` "Reality Check Hackathon" (created 13:25 via dashboard, b2b): cannot
  launch as is: task type `interview` with no `task_url`, duration 0, no screener, requires LinkedIn.
  Delete it or rebuild from the payload below. (Myat: was this yours?)

## The payload per job (terac_create_opportunity, then terac_launch_draft_opportunity)
```json
{
  "project_id": "fskntvr1bh3szfuyj8jsem2r",
  "internal_title": "reality-check job {job}",
  "title": "Read a startup's pitch and answer 5 quick questions (3 minutes)",
  "description": "You will read how a new company describes itself (its headline, first screen, and a short pitch) and tell us honestly what you understood, whether you would pay, and what you would change. No right answers. No web searching. Opens an external page; submit there to finish. About 3 minutes.",
  "business_type": "b2c",
  "num_participants": 3,
  "expected_days_to_complete": 5,
  "filters": [
    {"multi_select--country": {"$in": ["US", "CA", "GB"]}},
    {"multi_select--language": {"$in": ["en-US"]}},
    {"integer--age": {"$gte": 18}},
    {"reference--has_not_taken_study": {"$in": ["<prior reality-check opportunity ids>"]}}
  ],
  "screening_questions": [
    {"key": "q_buy", "pick": "one",
     "text": "Which of these did you do most recently?",
     "answers": [
       {"text": "Paid for a product or subscription online", "qualify_logic": "must"},
       {"text": "Signed up for something free online", "qualify_logic": "may"},
       {"text": "Neither of these in the last month", "qualify_logic": "reject"}]}
  ],
  "tasks": [
    {"sequence": 1, "task_type": "activity", "review_type": "auto_approve", "duration_minutes": 3,
     "title": "Read the page and answer honestly",
     "description": "Open the page, read the short pitch once the way you would if you stumbled on it, answer five quick questions, and submit. The page sends you back automatically when you finish.",
     "task_url": "https://reality-check-qhy9.onrender.com/rate/{job}?src=terac"}
  ]
}
```
Notes: language option id `en-US` is what our draft stored; confirm country/language ids with
`terac_get_filter_options` before the first launch. Keep ONE screener question: every extra question
is more time in Terac's interview stage. Do not add quotas.

## Our own study (17:00, first real launch)
Same payload, `num_participants: 5`, `task_url` = `/rate/self-before?src=terac` (our current landing
page + pitch). After the hero rewrite: n=3, `/rate/self-after`, with `has_not_taken_study` set to the
first study's id. Cost $30 + $18.

## What to watch after launch (poll `terac_get_opportunity`)
`submission_stats`: total / in_progress / awaiting_review / approved. If `awaiting_review` grows, the
callback is not firing (auto_approve fell back to manual): fix the redirect, then approve manually so
people get paid. Dashboard for progress: the `links.dashboard.submissions` URL from the response.
