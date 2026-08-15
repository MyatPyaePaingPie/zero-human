---
type: spec
status: active
created: 2026-08-15
issues: [4, 20, 18]
---
# Output first: the PDF and the .md, then the smallest pipeline that makes them

Time left: about 3.5 hours to lock (18:30). Everything below is sized to that. If a section is not
needed to produce the two files, it is not built today.

## 1. The two files a team receives

Both render from one `report.json`. Delivered as links on the result page and by text if a phone was
given: `/report/{job}.pdf` and `/report/{job}/agent.md`.

### The PDF (for the team's eyes, 3-5 pages)
Page 1, **verdict**: project name, one-line pitch (their words), stamp for the hackathon
(`contender` / `fixable by 18:30` / `not yet`), stamp for the business (`ready_to_charge` /
`one_gap_away` / `not_yet`), the three things to do before submission, in order. Footer: the stamp
rules verbatim, "N hackathon projects reviewed today", where this one ranks.

Page 2, **how to win this hackathon**: a table, one row per judging item (`judge/*`, weight order):
pass / partial / fail, the one-line why, the fix. Then sponsor tracks in three buckets: qualifies,
claimed but not evidenced, cheapest to add before lock. Then messaging: three rewrite suggestions,
each naming the slide or screen ("slide 1 headline: say who pays").

Page 3, **is it a business**: the four gaps (payer / take_money / stranger_proof / loop), each a
short paragraph: what the agentic panel concluded, what the humans said (quotes, blind vote counts,
whether they changed their mind after seeing the panel), the fix.

Page 4 (only with a repo), **from vibe-coded to MVP**: `tech/*` findings as plain advice, agent-fixable
first, "hand this page to your coding agent" note pointing at agent.md.

Last page, **evidence**: what we read (README, N slides, page text), who judged (5 agent personas,
N humans by domain, response time), and the re-run instruction.

### agent.md (for the team's coding agent)
Header: project, stamps, "do not invent facts; every item cites evidence". Then findings grouped
`## Fix before 18:30 (agent-owned)`, `## Needs a human decision`, `## Business gaps`, `## Repo advice`.
Each finding: `### <id> [pass|partial|fail]`, Evidence, Fix, Done when. Same ids as the PDF.

## 1b. Template (build from this)
Rendered template of both files: `docs/specs/report-template.html` (artifact:
https://claude.ai/code/artifact/4b64539c-1840-4ff8-b00d-acd363fb2424). Sponsor tracks are the first
table on page 1: that is where the prize money is, so it is where the report starts.

## 2. The smallest pipeline (simplified 14:45: cut the panel to 2 personas, humans optional)

```
Lovable form (repo URL, Slides URL, landing URL, optional phone)   -- one, two, or three
  -> POST /intake/hackathon                                        -- #20 wiring
  -> bundle: README+manifests (GitHub API) | slides text (export/pdf) | page text+probes (already built)
  -> sponsor check: grep evidence_hints over README+manifests+page (zero model calls) -> qualifies / claimed-not-evidenced / not used
  -> ONE batched model call per rubric section (judging, messaging, technical, gaps), 2 personas (judge, customer)
  -> humans: Terac general population n=3 with the one-page brief, blind vote; report renders immediately with
       "humans pending" and re-renders when they land (no waiting, no reveal step today)
  -> report.json -> agent.md + PDF (one HTML template, weasyprint or similar)
  -> result page + text link
```

Build list, in order, with owner:
1. **#20 wiring**: form fields -> bundle. Slides: `https://docs.google.com/presentation/d/<id>/export/pdf`
   for public decks; else "make it public or upload the PDF". (code)
2. **Rubric evaluation**: parse `docs/hackathon-rubric.md` JSON, batched evaluate per section with the
   5 agentic personas; hints grep before model. (code; #2's evaluate_batch is this)
3. **Report JSON + agent.md + PDF** per this file and `docs/specs/agent-report.md`. (code)
4. **Humans**: Terac general population n=3 per job with the brief; blind vote only; report updates when
   they land. (code, small: panels.py + terac_client exist)
5. **Lovable form + result page** pointing at the new endpoints. (keydriver / Myat)
6. **Dogfood**: run it on our own repo + deck + page; fix what it says. (advisor + code)

Not today: more probes, competition/economics/projections lenses, Replay runs, compounding beyond
"N reviewed + rank", pricing changes, accounts.

## 3. Open decisions (advisor answers unless overruled)
- Price today: keep the existing $8 link; first N teams free if that gets the room in (Myat).
- Human n: 3 via Terac general population per job (Terac credit covers ~20 jobs at $4.50);
  room raters are a bonus, not required to settle.
- Timeout: humans 30 min then settle on the agentic panel with "humans pending" in the PDF.
