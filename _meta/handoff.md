---
type: handoff
status: active
created: 2026-08-15
---
# Handoff (status-first), 2026-08-15 12:30 PDT

**Session role:** zero-human is the sole code writer. Advisory sessions (augur, ms) closed. keydriver session collects keys and drives Lovable (storefront); it reports to this session.
**Channel:** GitHub issues on MyatPyaePaingPie/zero-human. Comment on existing issues; do not create new ones unless a gap has no owner. Epic #18 is the status board. Plan: `_meta/plans/2026-08-15-issue-queue-dag.md`.
**Protocol:** matra execution protocol (issues-first serial cycle, forensics first, tests first, WIP 1, receipts on issues, deploy per wave). Kernel plugin skills apply.

## What is merged (main, all pushed)
Latest commits: d86f4ae sweep background; +1 fix (notify on timeout). 28 tests green. Everything from this morning: pay-first Stripe flow + poller, evidence_standard floors, envelope/learning/protocol, Terac client (real quote \$4.50, panel 3, screener), Replay objective evidence + self-audit project, Linq rater panel + webhook, full_reality_check bundle SKU + /verdict + /summary + CORS, sweep + /sweep page, render scripts, keepalive.

## What is live
https://reality-check-qhy9.onrender.com (Render FREE tier: DB wiped on every deploy; keepalive.sh running from this laptop). Deployed commit: e53fd4b family + d86f4ae (background sweep). PH sweep of 20 launches was queued at ~12:00; check /sweep. Stripe links: \$8 https://buy.stripe.com/5kQbJ3d6cbuZ6PIaaC33W00, \$25 https://buy.stripe.com/28EfZj3vC8iN5LE6Yq33W01. Linq line +1 415 577 0605 (webhook registered, secret in keychain + Render env). Terac: org zerohuman, balance \$25, no launches (Aria: ~17:00). Replay self-audit project proj-reality-check-zero-human--msuppfmi (5 journeys running, 0 bugs at last check).

## Keys (keychain, service == var name)
GROQ_API_KEY, OPENAI_API_KEY, ZEROHUMAN_STRIPE_WRITE_KEY, ZEROHUMAN_STRIPE_PUBLISHABLE_KEY, RC_PAYLINK_DEFAULT, RC_PAYLINK_FULL_REALITY_CHECK, TERAC_API_KEY, REPLAY_API_KEY, LINQ_API_KEY, LINQ_WEBHOOK_SECRET, RENDER_API_KEY, SUPERSERVE_API_KEY, RC_ENVELOPE_SECRET. Absent by decision: PIONEER, ZEROHUMAN_STRIPE_RESTRICTED_KEY (poller uses the write key).

## Aria's standing decisions
- Do not worry about Render persistence, pricing (#1), or hero copy now. Build.
- Terac launch is a ~17:00 run, after everything else.
- The main deliverable is the AGENT-FACING fix doc (`/report/{job}/agent.md`); human report second (#4). Reuse site-spec audit checks with the same ids (#3).
- Judgement and decisions happen in issues; implementation is cheap.

## Local state to know
- `reality_check/lenses.py` UNTRACKED draft (15-lens rubric), written before Aria said stop; not wired, not committed. Decide under #2.
- Scratch: PH sweep JSON at the session scratchpad ph.json.
- Next action when work resumes: decide #2 (batched evaluation) on the issue, then Wave 1 per the DAG: #3 probes first.
