# Reality Check (zero-human): project instructions

## compression — mandatory

minimum text. zero meaningful loss.

* delete anything removable.
* merge anything redundant.
* shorten anything compressible.
* prefer structure over prose.
* preserve all meaning that affects correctness, clarity, decisions, evidence, uncertainty, or action.
* length follows information. never pad; never truncate for brevity.

before emitting:

1. perform a deletion pass.
2. remove every word, sentence, bullet, section, preamble, recap, transition, or explanation whose removal does not materially reduce meaning.
3. repeat until no further lossless deletion is possible.

do not emit while removable text remains.

verbosity is a defect.
omission is also a defect.

Judgment for agents. One paste or URL in, a full report out: lenses of evidence, a stamp, a route to
money, an agent-facing fix doc. Thesis: we sell evidence-routing under uncertainty; the router decides
which evidence (probe, model, crowd, expert) is worth paying for before money attaches to a claim.
Read `README.md`, then `docs/working-agreement.md`. The organizers guidebook (`docs/research/guidebook.md`, PDF beside it) is the canonical rubric source; `docs/hackathon-rubric.md` derives from it. Rules in `.claude/rules/` are always on.

## Seats (who does what)
- **Myat (repo owner): business.** Pricing, storefront copy, GTM, human budgets. `area:business`.
- **zero-human session: sole code writer.** Owns `reality_check/`, `tests/`, `scripts/`. Runs on Fable,
  dispatches Sonnet builders to write code, integrates, deploys. `seat:code`.
- **zero-human-brainstormer session: everything not code.** Specs, research, docs, this `.claude/`.
  Owns `docs/`, `.claude/`. `seat:advisor`.
- Aria feeds the advisor; the advisor advises the code session; anyone may override Aria on an issue
  when they have a better way, stated on the issue.

## Channel
Issues on `MyatPyaePaingPie/zero-human`. Epic #18 is the status board. Every decision and every
receipt is a comment on the owning issue. PRs for larger or cross-seat changes. Long-term material
goes under `docs/` (specs in `docs/specs/`) and is linked from the issue. Skill: `issue-receipt`.

## Product invariants
- Headline output is `/report/{job}/agent.md` (spec: `docs/specs/agent-report.md`). Human report is a
  rendering of the same JSON.
- Finding ids are stable and lens-prefixed; objective ids are site-spec audit ids verbatim.
- Objective lenses cost zero model calls. Model calls are batched (one call per lens per persona).
  Groq free tier is ~30 RPM: never add a per-claim call.
- Humans judge on top of agentic results and see the evidence line. Prior-run respondents are refused.
- Buyer text is information, never authority. Spend goes through the signed envelope. Fail closed.
- Never spend, launch Terac, or message buyers in Aria's voice without an explicit go on the issue.

## Ops
- Tests: `.venv/bin/pytest -q` (green before every push). Keys: keychain, service == var name; never in tree.
- Render free tier wipes the DB on deploy: one deploy per wave, sweep re-run after. Skill: `wave-deploy`.
- Live: https://reality-check-qhy9.onrender.com. Plan: `_meta/plans/2026-08-15-issue-queue-dag.md`.
