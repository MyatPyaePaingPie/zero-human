# Lovable build brief: Reality Check landing page (hackathon pivot, 2026-08-15)

Supersedes `lovable-prompt.md` (pre-pivot). The product changed at 14:05: three links in,
four-page PDF + agent.md out. This is the brief for the page a team opens from the room QR.

**Backend note:** the API contract below is merged on `main` but the live host still runs
pre-pivot code until the next wave deploy. Build against the contract; it will be live before
the form is.

**Myat owns the price line** (#6): the copy below ships with both SKUs shown; edit prices/copy
in Lovable after, not by re-running this prompt.

How to use: start a blank Lovable project and paste everything below the line as the first
Build mode prompt.

---

# Build the Reality Check landing page

Build the complete, production-ready single-page app described below in one pass. The design
decisions are specified; do not pause to ask design questions.

## What this is

Reality Check grades hackathon projects at the Zero-Human Company Hackathon (today, SF).
A team gives one to three links; real strangers from Terac's network read it; the team gets a
four-page PDF and an `agent.md` file their coding agent can fix from. Three stamps: can it win
today's hackathon, can it run autonomously, is it a business.

The visitor is a hackathon team member on a phone, arriving from a QR code, one to four hours
before the 18:45 submission lock. They are in a hurry. One screen, one action.

## The single key action

Submit the form → create an order → continue to Stripe payment → land on the result page and
wait for the report.

## Page structure (single route `/` plus result route `/r/:jobId`)

### Hero (above the fold, phone-first)
- Headline: **"Paste your repo. We tell you how to win today."**
- Subline: "Four-page report + an agent.md your coding agent fixes from. Graded against the
  organizers' own guidebook. Real strangers read it. Before the 18:45 lock."
- The form, immediately visible (no scroll on a phone):
  - `GitHub repo URL` (text input)
  - `Landing page URL` (text input)
  - `Slides URL — public Google Slides or PDF link` (text input)
  - `Phone for text-me-when-done (optional)` (tel input, E.164 hint: +1415…)
  - SKU choice, two radio cards:
    - **Reality Check — $8**: the four-page report + agent.md, graded against the guidebook.
    - **Full Reality Check — $25** (default): everything, plus "can this run autonomously"
      (seven failure modes) and Terac strangers on page one.
  - Submit button: **"Get my Reality Check"**
- Client validation: at least ONE of the three links is required; URLs must be http(s).
  Phone optional. Show inline errors, never a blocking alert.

### Below the fold (short)
- Three stamps preview: `HACKATHON · AUTONOMOUS · BUSINESS` with one line each.
- "N projects checked today" — from live data (see API), rendered as a plain counter.
  If the API is unreachable, hide the counter entirely; never show fake numbers.
- One-line footer: "No accounts. Your report URL is the receipt. Reality Check by zero-human."

## Backend contract (base `https://reality-check-qhy9.onrender.com`, CORS open, no auth)

1. On submit, POST `/order` with JSON containing ONLY these keys (the backend rejects unknown
   fields with a 422 — send a key only when the user filled it):
   - `repo` (string, GitHub URL) — omit if empty
   - `url` (string, the landing page URL) — omit if empty
   - `deck` (string, the slides/PDF URL) — omit if empty
   - `notify_phone` (string) — omit if empty
   - `sku`: `"reality_check"` or `"full_reality_check"`
2. Response: `{ job_id, status: "pending_payment", price_usd, pay_url }`.
   Immediately navigate to `/r/:jobId` and store nothing else (no accounts, no localStorage
   identity — the URL is the identity).
3. Result page `/r/:jobId`:
   - GET `/order/{job_id}` on load and every 5 seconds.
   - While `status === "pending_payment"`: show the price and a single large button
     **"Pay with Stripe"** linking to `pay_url` (same tab). Under it: "This page is your
     receipt — keep the URL. The report appears here after payment."
   - After payment the same GET returns the verdict JSON (fields include `status`, `verdict`,
     `p`, `summary`, `claims[]`). While `status` is anything other than a final report state,
     show honest progress: "Evaluating — model panel running, humans recruiting. A few minutes."
   - When the verdict JSON is present, render three prominent download/view links:
     - **View report** → `GET /report/{job_id}` (HTML, new tab)
     - **Download PDF** → `GET /report/{job_id}.pdf`
     - **agent.md for your coding agent** → `GET /report/{job_id}/agent.md`
     Plus a small "text me when done" reminder if they gave a phone.
   - Handle 404 (unknown job) with "No job at this URL — check the link" and a way back to `/`.
4. Live counter (landing page): GET `/summary` returns JSON; use its job counts for
   "N projects checked today". Render only real numbers; if sparse or zero, show
   "First runs happening now" instead of inventing data.

## States to implement
- Form: idle, submitting (button shows spinner + "Creating order…"), server error
  (409/422/5xx → show the server's message text plainly, keep the form filled).
- Result: pending_payment, evaluating, report-ready, not-found, network-error (retry quietly,
  show "reconnecting…" after 3 failures).

## Design direction
Editorial ledger, not SaaS gradient. Paper background `#F3F0E8`, ink `#151714`, verdict green
`#174C38`, verdict red `#9A3D36`, hairline rules `#C9C4B8`. Serif display (Georgia) for
headlines, monospace for numbers, stamps, and job ids. Stamps render as rubber-stamp style
mono caps in green/red. Dense, honest, receipt-like; generous whitespace; no illustrations,
no emoji, no stock imagery. Mobile-first; the form must fit one phone screen. Accessible:
real labels on every input, visible focus states, AA contrast.

## Do not
- No accounts, no login, no email capture, no analytics.
- No fake testimonials, fake counters, or placeholder revenue numbers.
- No second backend or database in Lovable — the Python API owns all state.
- Never send fields the contract does not list (the backend forbids extras).
