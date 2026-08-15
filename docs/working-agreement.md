---
type: reference
status: active
created: 2026-08-15
---
# Working agreement

Who owns what, and how we talk. Filed on epic #18 (2026-08-15 12:45 PDT).

| Seat | Owner | Surface | Label |
|---|---|---|---|
| Business | Myat (repo owner) | pricing, storefront copy, GTM, human budgets | `area:business` |
| Code | zero-human Claude session (Fable + Sonnet builders) | `reality_check/ tests/ scripts/`, deploys | `seat:code` |
| Advisor | zero-human-brainstormer Claude session | `docs/ .claude/`, specs, research, epic checklist | `seat:advisor` |

Rules
- Issues are the channel; #18 is the status board. Decision comment before building, receipt after.
- PRs for larger or cross-seat changes. Long-term material under `docs/`, linked from the issue.
- Anyone may override Aria on an issue when they have a better way; say so there.
- Reuse before build: site-spec audit ids (`CodingVault/site-spec/packages/core/src/audit/audit.ts`)
  and `handoff.json` shape; our prior autonomous systems (consensus/brier/bandit; envelope/protocol/learning).
- One deploy per wave (Render free tier wipes the DB). Terac launch ~17:00, after everything else.
