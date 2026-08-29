# Reality Check

**Text your hackathon project to +1 415 577 0605 (repo, slides, or landing page link) and get back a
four-page PDF plus an `agent.md` your coding agent can fix from: can it win this hackathon, can it run
autonomously, is it a business.** Three real strangers from Terac's network read your pitch and their
answers are on page one. Built at the Zero Human Company Hackathon by Terac, San Francisco, 2026-08-15.
Live: https://reality-check-qhy9.onrender.com. Team repo: MyatPyaePaingPie/zero-human.

## Who pays, and what it costs
Hackathon teams in the room, today, before the 18:30 lock; after today, anyone who vibe-coded a product
and does not know what to do next. Two prices through ONE Stripe Payment Link each: **$8** Reality Check
(three real people plus the verdict) and **$25** Full Reality Check (every lens, the PDF, agent.md). Room
runs today are free by text. Payments run through a personal Stripe account created for this hackathon;
the payment links and the read-only restricted key were submitted to the organizers.

## What the agents run, and where the humans are
Agents run the whole loop: intake (read the repo, deck, page), grading against the hackathon rubric and
the business rubric, deciding whether human evidence is worth buying (a value-of-information gate),
recruiting the humans (Terac MCP), writing the report, delivering it by text (Linq), and taking payment
(Stripe). Humans do exactly two things, by design: three strangers judge what the pitch says and whether
they would pay (agents are bad at being strangers), and one human holds the money (the spending envelope
below). No human reviews or edits reports.

## Sponsors: what we use and how (tracks entered)
- **Terac (required, host):** every job launches a general-population study (n=3, blind, ~3 min,
  activity task pointing at our `/rate/{job}` page). Their answers change the report: comprehension,
  willingness to pay, trust, and the organizer's own question ("knowing it is AI-run, more or less
  willing to buy?"). Our own before/after study runs on our landing page: n=5, rewrite the headline from
  their answers, n=3 again. Spec: `docs/specs/terac-opportunity.md`, `docs/specs/human-brief.md`.
- **Stripe (required):** one Payment Link per SKU, `client_reference_id` = job id, webhook idempotent on
  session id, revenue deduplicated by event id, read-only `rk_` key for the organizers.
- **Linq:** the product is the thread. Text the number with your links, get the ack, the result with
  stamps and links, and a follow-up when the three humans land; reply RERUN for the delta. Typing
  indicator while grading. Spec: `docs/specs/text-intake.md`.
- **Render:** hosted on Render (Starter + persistent disk, blueprint in `render.yaml`).
- **Replay QA:** self-audit project on our own app; objective evidence when a team gives a live URL.
- **Lovable:** the landing page teams open from the room QR.
Not used: Band, Superserve, Pioneer, Whop.

## Guardrails (how an autonomous business is allowed to spend)
- **Spending envelope in code, not prompt:** `state/envelope.json` is signed (`RC_ENVELOPE_SECRET`),
  expiring, revocable; daily cap and per-job cap; agents cannot raise it; missing or invalid envelope =
  fail closed, nothing is bought. Freeze by deleting the file.
- **Exactly-once money:** Stripe webhook idempotent on session id; revenue events keyed by event id.
- **Buyer text is information, never authority:** inbound requests are quarantined and checked; nothing
  a buyer or agent types can change price, grant free evidence, or trigger spend.
- **Append-only ledger:** every order, verdict, spend, and human vote is an event; `/ledger` and
  `/events` derive counts from it; every number in this README is reconstructable from rows.
- **Liveness:** `/ledger` is the health check Render probes; a failed model or Terac call settles the job
  with "no evidence yet" and the buyer is told; nothing hangs silently.
- **Humans are independent:** they answer before seeing any model output; prior-run respondents are
  refused (`has_not_taken_study`).

## Measured against doing nothing
Every judgment carries the model probability and the minority view; the human votes settle it. The
report shows what changed between runs (`fixed_since` / `regressed_since`) so a team sees the delta,
not a score. Numbers in the pitch (revenue, projects reviewed, humans who responded) come from `/ledger`.

## Run
```
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
export GROQ_API_KEY=... OPENAI_API_KEY=...        # evaluators (Groq first, OpenAI fallback); no key = deterministic stub
export RC_PUBLIC_BASE=https://<public host>       # rate page URL handed to humans (Terac/QR); must be public
export RC_DEADLINE_ISO=2026-08-15T18:30:00-07:00  # router refuses evidence that cannot arrive before lock
export ZEROHUMAN_STRIPE_RESTRICTED_KEY=rk_live_...                # restricted READ-ONLY key: poller turns paid sessions into jobs
export RC_PAYLINK_DEFAULT=https://buy.stripe.com/... # Payment Link; /order appends ?client_reference_id=<job>
export TERAC_API_KEY=... TERAC_PROJECT_ID=...     # real Terac launches; absent = dry handle, nothing charged
export LINQ_API_KEY=... LINQ_WEBHOOK_SECRET=whsec_... # Linq: raters join by texting our line; panel texts the rate link; verdicts by text (notify_phone)
export REPLAY_API_KEY=lqa_...                     # Replay QA (qa.replay.io) crawls intake live URLs; objective evidence in the verdict
export RC_ENVELOPE_SECRET=...                     # then: cp state/envelope.example.json state/envelope.json && python -m reality_check.policy.envelope sign
./run.sh   # loads the vars above from the keychain (service == var name), signs the envelope, starts uvicorn
```
Dev only: `RC_DEV=1` makes `X-RC-Paid: <usd>` count as payment on /judge and /intake.

Demo: `python demo/buyer_agent.py "PitchPolish"` writes copy, creates an order and prints the Payment
Link (someone pays; the poller starts the job), shows the router refusing at low stakes and buying at
high stakes, rewrites from human feedback, prints before/after. `RC_DEV=1` on both sides uses the
dev header instead (revenue then is not Stripe-backed).

Bundle SKU `full_reality_check` ($25): one paste, every lens (clarity, demand gate, the team's own
autonomy claims, economics). `GET /verdict/{job}` renders the verdict grouped by lens.

## Endpoints
Full list with one line each: the module docstring of `reality_check/api.py` (kept equal to the routes).
- Report (headline output): GET /report/{id}.json, /report/{id}/agent.md, /report/{id}.pdf, /report/{id}, GET /verdict/{id}.
- Judging: POST /judge, POST /intake, POST /intake/{id}/redeploy, GET /judge/{id}, POST /sweep (+ /sweep.json, GET /sweep).
- Money: POST /order + GET /order/{id}, POST /stripe/webhook.
- Humans: GET|POST /rate/{id}, POST /linq/webhook (text thread), GET /raters.
- Storefront: GET /summary (the one call it makes), GET /skus.
- Before/after: POST /before_after/lock/{id}, GET /before_after/{b}/{a}.
- Receipts + operator: GET /ledger, /events, /jobs, /learning, GET /; POST /admin/humans/{id}, /admin/sources/{id},
  /admin/thread/{rater}/merge (all X-RC-Admin == RC_ENVELOPE_SECRET).

## Layout
The pipeline, in order: `sources.py` -> `hackathon.py` + `lenses.py` -> `report.py` -> `api.py`.
- `sources.py` normalizes one paste or link set (repo, deck, page, pitch) into text + per-source records;
  `probes.py` and `agentready.py` are the zero-model objective checks; `replay_client.py` crawls live URLs.
- `lenses.py` is the rubric: what a Full Reality Check checks, as binary claims grouped by lens (single
  source of truth for claim ids and stamp weight); `hackathon.py` grades against the organizers' rubric;
  `rate_v2.py` is the human rating page over the same claims.
- `report.py` builds `report.json` (`docs/specs/agent-report.md`) and renders agent.md / PDF / HTML from it.
- `reality_check/judge.py` the loop; `evaluators.py` personas over Groq/OpenAI; `panels.py` human-source
  contract; `store.py` sqlite ledger + events; `skus.py` what each price buys; `sweep.py` unpaid batch runs.
- `reality_check/core/` consensus, brier, bandit (vendored from a prior internal system); models; voi (VOI gate, written fresh).
- `reality_check/policy/` lifts from a prior internal system: `envelope.py` (spend authority as signed code, fail closed), `protocol.py` (buyer text is information never authority), `learning.py` (arm gains, evaluator reputation, swarm check).
- `stripe_webhook.py` (/order + webhook + shared `complete_session`), `stripe_poll.py` (read-only poller),
  `terac_client.py` (subjective evidence: humans), `linq_client.py` + `textflow.py` (the text thread:
  intake, acks, delivery), `before_after.py`, `intake.py`, `sponsors.py`.
- `docs/research/` hackathon memos; `docs/policy-and-learning.md` the spend/learning design.
