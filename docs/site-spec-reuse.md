---
type: reference
status: active
created: 2026-08-15
issues: [3, 16]
---
# What we reuse from site-spec

Source: `CodingVault/site-spec` (internal, not published). Two things port cleanly.

## 1. The audit (37 named checks) -> `probes.py`
`packages/core/src/audit/audit.ts`. Finding shape `{checkId, severity: error|warning, file?, message, fix?}`.
Keep `checkId` verbatim so agent.md ids are stable and a site-spec-built site and a Reality Check
agree. Ids grouped by the lens that renders them:

- **seo / findability:** `audit/title-missing` `audit/description-missing` `audit/canonical-missing`
  `audit/jsonld-missing` `audit/jsonld-invalid` `audit/og-missing` `audit/twitter-card-no-image`
  `audit/noindex` `audit/h1-count` `audit/sitemap-missing` `audit/sitemap-page-missing`
  `audit/robots-missing` `audit/robots-stale-token` `audit/robots-blocks-ai-search`
- **agent-ready:** `audit/llms-missing` (plus isitagentready ids, #7)
- **stability:** `audit/404-missing` `audit/broken-link` `audit/dangling-ref` `audit/no-pages`
  `audit/cache-policy-missing` `audit/headers-missing` `audit/headers-stale`
- **security:** `audit/mixed-content` `audit/inline-handler` `audit/hsts-preload`
  `audit/csp-report-only-theater` `audit/google-fonts-cdn`
- **trust / legal:** `audit/cookie-undeclared` `audit/tracker-undeclared` `audit/form-untyped`
  `audit/jsonld-self-serving-rating` `audit/claims-parity` `audit/foundation-invalid`
- **a11y / perf:** `audit/img-alt-missing` `audit/img-dims-missing` `audit/lcp-image-lazy`
  `audit/viewport-lock`

Site-spec audits a static dir; we audit a live URL. Port the check logic (regexes, header names,
JSON-LD parse) over fetched HTML + headers; the "declared surface" checks (`cookie-undeclared`,
`tracker-undeclared`, `form-untyped`) run with an empty `foundation.json` assumption, i.e. any
tracker or cookie is a finding until the buyer declares it. SSRF guard per #3.

## 2. `handoff.json` shape -> `agent.md`
`packages/core/src/handoff/handoff.ts`: everything an agent might invent is pre-decided (facts with
sources, locked copy, compiler-owned files) and the auditor enforces it afterwards. Our agent doc is
the same contract pointed the other way: findings with ids, evidence, fix, acceptance, owner; the next
run enforces it. Spec: `docs/specs/agent-report.md`.

## 3. Dogfood (#16)
Our own site fails today: no robots.txt, sitemap.xml, llms.txt, 404, /privacy, /terms. site-spec's
build pipeline emits all of these for a static site; for our FastAPI app the cheap move is static
routes serving the same files. Run our probes against ourselves before the Terac run.
