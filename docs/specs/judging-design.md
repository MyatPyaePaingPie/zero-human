---
type: spec
status: active
created: 2026-08-15
issues: [4, 24]
sources: our prior judge-panel systems (measured), docs/research/*, external literature (cited inline)
---
# Judging design, locked: how the model portion and the human portion work

Aria 17:20: "is the current judging system really optimal?" Answer: close in shape, wrong in four
places. This is the design we lock before any human testing. Deltas to code are at the end.

## What we already do right (keep)
- Batched claims per persona, one call per section; a malformed or missing claim becomes an explicit
  `skip` and one repair pass re-asks only the missing indices; never a fabricated 0.5.
- Transport failure: retry with backoff, fall back to the second provider, then explicit `skip`.
- Evaluators never see other evaluators' or humans' answers. Commit before the oracle.
- Objective claims are decided by probes, never by the model.
- Dedupe by stable claim id; a re-scored claim counts once.

## What changes (the four fixes)

### 1. Evidence-grounded verdicts, abstain when the text is silent
Every model claim returns `{idx, verdict: yes|no|not_evidenced, quote, reasoning}`. `quote` is a
verbatim span from the bundle (max 200 chars) that supports the verdict; if no span exists the verdict
is `not_evidenced`, not `no`. The report says "not evidenced: say it if it is true", which is the fix
for most hackathon decks. Rationale: span-level grounding is more diagnostic than scores and abstention
beats confident wrongness (arXiv 2503.05061, 2608.07517). We verify quotes exist in the bundle
(substring check); a claim whose quote does not exist is downgraded to `not_evidenced`.

### 2. Confidence comes from agreement, not from the model saying so
Drop `p` as a verbalized probability. Each persona returns a verdict; the claim's score is the
agreement fraction across the panel (personas x samples). Verbalized confidence and even logprobs are
miscalibrated or anti-calibrated (arXiv 2509.25532, 2512.22245); our own systems recorded confidence
as anti-predictive. Panel = 3 seats, distinct model families where possible (OpenAI primary judge,
second family for the second seat, third seat = OpenAI at temperature with a different persona), 1
sample each. Score: yes-fraction. pass >= 2/3 yes with at least one quote; partial = 1/3; fail = 0/3;
`not_evidenced` majority = not evidenced. Disagreement (1/3 or 2/3 splits on a human-flagged claim) is
what routes the claim to humans first (invert the old "low dissent = skip").

### 3. Order randomization and small batches
Claims are shuffled per call (seeded by job + persona) and batched at most 8 per call, numbered; the
prompt states the count and index range. Position bias is a real, separately failing gate in our own
panel work; the literature has no batching study, so small numbered batches with randomized order is
the safe default.

### 4. Personas: fewer, distinct, and named for the reader
Three personas per section, chosen for what they can each see: `judge` (this panel: YC founder, Stripe
AI lead, DeepMind PM), `customer` (a stranger deciding whether to pay in the next minute), `engineer`
(reads the repo for autonomy guardrails and vibe-coded fragility). The `engineer` persona receives the
repo file tree + first docstrings + guardrail files (policy/envelope/webhook/ledger/health/auth); the
others receive README + deck + page. Report shows "judge: yes, customer: no, engineer: not evidenced"
under each partial claim, so a team sees who disagreed.

## Sponsors: signatures first, model second
Sponsor status is decided by signature detection (`docs/sponsor-signatures.md`, from each sponsor's own
docs: packages, hosts, env vars, config files, MCP tool prefixes, webhook paths, deck phrases), zero
model calls: no signature = `not used`; signatures present = the model panel judges the sponsor's
`meaningful_use` statements from evidence, with quotes. `qualifies` needs signature + majority yes on the
required statements; otherwise `claimed, not evidenced` with the exact missing statement as the fix.

## Stamps (unchanged rules, stated in the report footer)
Hackathon: `contender` if both required rules pass and no weight-3/4 item fails; `fixable by 18:30` if
every fail is agent-owned; else `not yet`. Autonomy: k of 7 hold (an item holds at >= 2/3 yes with a
quote). Business: four gaps.

## The human portion, locked
- **Who:** 3 people per job, Terac general population, US/CA/GB, English, 18+, one screener question
  with a reject answer, `has_not_taken_study` excludes prior raters. (`docs/specs/terac-opportunity.md`)
- **What they see:** headline + first screen, one-line pitch, price line. Nothing from the model.
  Blind to model verdicts and to each other. (`docs/specs/human-brief.md`)
- **What we ask:** free recall first ("in one line, what does this do and for whom"), then forced-choice
  + one-line why: would you pay, is the price clear, would you hand over your card, and the organizer's
  question (knowing it is AI-run: more / less / same). Optional: change one thing. Five-second-test
  practice: free recall first, recognition after, max 6 questions; no double-barreled or leading items.
- **How it counts:** n=3 is descriptive, not statistical (a 2-of-3 majority lower-bounds population
  agreement at ~9%; PMC12157567). So the report prints raw counts and verbatim quotes ("2 of 3 could
  say what it does; 1 of 3 would pay; 'where is the price?'"), never "humans confirm". Human votes
  settle the human-flagged claims (clarity, demand) as counts shown next to the model panel's split.
- **Model call after humans:** one call scores `q1_what` against the team's own pitch as
  yes / partial / no (comprehension). That is the only place a model touches human answers.
- **Timing:** report waits for the panel or `RC_HUMAN_TIMEOUT_S`; on timeout the human block says
  "3 people were invited; N answered in time" and the report is delivered anyway. Human results are
  always inside the PDF and agent.md.
- **Our own before/after:** same task on our landing page, n=5, rewrite the headline from q1/q6, n=3
  again; both counts on a slide.

## Gates before we call the judge trustworthy (today: minimal)
Position-bias check: re-run one job with claim order reversed; a claim whose verdict flips is marked
`unstable` in the JSON and shown as partial. Provenance: every verdict row carries persona, model, and
the quote. Anything else (calibration deciles, floor tests for seats) is after today.

## Deltas to code (for #4 / evaluators.py / hackathon.py / rate page)
1. `evaluate_batch`: response schema per claim `{idx, verdict, quote, reasoning}`; verify quote in
   bundle; `not_evidenced` verdict; drop verbalized `p` (keep a derived `score = yes_fraction` for
   compatibility).
2. Panel of 3 seats (OpenAI primary; second family if a key exists, else OpenAI different persona);
   claim status from yes-fraction; per-persona verdicts stored and rendered under partial items.
3. Shuffle claims per call, batches of <= 8, numbered, count stated.
4. `engineer` persona gets the repo tree + docstrings + guardrail files; `judge` and `customer` get
   README + deck + page.
5. Sponsor status from `docs/sponsor-signatures.md` detection first, then panel on `meaningful_use`.
6. Rate page and Terac payload unchanged from the specs; humans block waits for settle or timeout;
   after humans, one comprehension-scoring call.
7. Position-bias re-run flag `unstable` on flipped claims (cheap: one extra pass on the judge seat).
