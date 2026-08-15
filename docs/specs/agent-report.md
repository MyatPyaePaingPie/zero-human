---
type: spec
status: active
created: 2026-08-15
issue: 4
---
# `/report/{job}/agent.md` and `.json`: the agent-facing fix doc

The primary product output. A buyer (or their coding agent) drops this file into a repo, the agent
fixes every finding it owns, the buyer re-runs, and the delta shows. The human report (`/report/{job}`)
is a readable rendering of the same JSON; never a second data model.

Modelled on site-spec `handoff.json`: everything an agent might invent is pre-decided (finding ids,
evidence, exact fix, acceptance check, owner) and the next run enforces it, the way site-spec's `audit`
enforces the handoff afterwards.

## Design rules

1. **Stable ids.** Objective findings use the site-spec audit `checkId` verbatim (`audit/<check>`,
   from `CodingVault/site-spec/packages/core/src/audit/audit.ts`), e.g. `audit/description-missing`,
   `audit/robots-missing`, `audit/llms-missing`, `audit/h1-count`, `audit/og-missing`,
   `audit/canonical-missing`, `audit/noindex`, `audit/img-alt-missing`, `audit/dangling-ref`,
   `audit/mixed-content`, `audit/inline-handler`, `audit/tracker-undeclared`, `audit/hsts-preload`.
   The finding's `lens` field says which lens renders it. Non-audit findings use `<lens>/<check>`
   (`demand/payer`, `agentready/<id>`, `replay/<id>`). Same id across runs = compounding works.
   Full audit id list: `docs/site-spec-reuse.md`.
2. **Every finding carries evidence.** `kind` in `probe | replay | model | human`; probe/replay findings
   quote the observation (URL, status, selector, header); model findings carry `p` and the minority
   view; human findings carry n and votes. Probe evidence outranks model opinion when both exist.
3. **Every finding carries an owner.** `agent` = a coding agent can fix it from the repo (missing
   robots.txt, no h1, no privacy page). `human` = needs a person (name a price, name the payer, get a
   testimonial). The doc is sorted agent-first so the agent has a clean run.
4. **Every finding carries an acceptance check** the next run will execute: for objective findings the
   finding id that must be absent (`{"probe": "audit/x-missing", "must": "absent"}`); for model/human findings the claim text that must reach `p >= 0.7`.
5. **Additive only.** New lenses add findings; existing ids never change meaning.
6. **Compounding matcher.** Prior runs match on full origin (scheme + host + port), never registrable
   domain (`*.vercel.app` hosts strangers), and never on default buyer ids (`anonymous`, `sweep:*`).
   Chains via `before_job` count too.
7. **Disclosed stamp rule.** The RED/AMBER/GREEN conditions are printed verbatim from code in the
   agent.md header and the PDF footer.
8. **Delivery.** `/report/{job}.json`, `/report/{job}/agent.md`, `/report/{job}.pdf` (same JSON, one
   HTML template). No accounts: the job URL is the identity.

## JSON shape (`/report/{job}.json`)

```json
{
  "job": "j_...",
  "generated_at": "2026-08-15T20:10:00Z",
  "input": {"url": "https://example.com", "text_sha": "..."},
  "stamp": {"color": "amber", "why": "demand passes; 6 objective fails; no privacy page", "flip": ["legal/privacy-missing", "demand/payer"]},
  "route": ["fix the 5 agent-owned objective findings", "name the payer on the hero", "add /privacy and /terms"],
  "evidence_bought": [{"kind": "model", "n": 6, "usd": 0.00}, {"kind": "human", "n": 3, "usd": 4.50}],
  "findings": [
    {
      "id": "audit/description-missing",
      "lens": "seo",
      "severity": "error",
      "owner": "agent",
      "claim": "Every page has a meta description",
      "evidence": {"kind": "probe", "observed": "GET / : no <meta name=description>", "url": "https://example.com/"},
      "fix": "Add <meta name=\"description\" content=\"...\"> (50-160 chars) to every page <head>.",
      "acceptance": {"probe": "audit/description-missing", "must": "absent"}
    },
    {
      "id": "demand/payer",
      "lens": "demand",
      "severity": "error",
      "owner": "human",
      "claim": "A specific person or role who would pay for this is named",
      "evidence": {"kind": "model", "p": 0.31, "votes": 4, "minority": "operator: 'teams' is implied but never named"},
      "fix": "State the buyer in the hero: role, company size, and the moment they reach for this.",
      "acceptance": {"claim": "demand/payer", "must": "p >= 0.7"}
    }
  ],
  "prior_runs": [{"job": "j_prev", "at": "...", "stamp": "red", "fixed_since": ["audit/title-missing"], "regressed_since": []}]
}
```

## `agent.md` rendering (same data, for the agent's eyes)

```
# Reality Check for https://example.com  (job j_..., stamp AMBER)
Why: ...   Flip the stamp: legal/privacy-missing, demand/payer

## Fix these (agent-owned, 5)
### audit/description-missing  [error]  probe
Observed: GET / : no <meta name=description>
Fix: Add <meta name="description" ...> to every page <head>.
Done when: audit/description-missing is absent on the next run.
...
## Needs a human (3)
### demand/payer  [error]  models p=0.31 (4 votes), minority: ...
Fix: ...   Done when: p >= 0.7 on re-run.

## Since last run
Fixed: audit/title-missing.  Regressed: none.
```

## Acceptance for #4 (falsifiable)

- `GET /report/{job}.json` validates against the shape above for a settled `full_reality_check` job;
  every finding has `id, lens, owner, evidence.kind, fix, acceptance`.
- `GET /report/{job}/agent.md` lists agent-owned findings before human-owned ones.
- Two runs on the same host: the second has `prior_runs[0].fixed_since` populated when an id cleared.
- Stamp rule matches #4's proposal (RED if demand or viability fails majority or a security probe fails hard).
