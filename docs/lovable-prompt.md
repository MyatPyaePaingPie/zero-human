# Lovable prompt: Reality Check storefront (view layer only)

Paste everything below the line into Lovable as the first prompt.

---

Build a storefront and live dashboard for **Reality Check**. It is a VIEW LAYER ONLY over an existing backend. Do NOT create a backend, database, Supabase project, auth, or edge functions. Every piece of data comes from `https://reality-check-0f80.onrender.com` via plain `fetch` (CORS is enabled, no auth). Payments happen on Stripe Payment Links; never build checkout.

## The one sentence
Reality Check sells evidence-routing under uncertainty: it decides whether another model, a crowd, or an expert is worth paying for before money gets attached to a claim.

Plain-English tagline for the hero: **"Pay $8. Find out if you're bullshitting yourself."** Subline: at least three real people read your page or pitch, more when the models disagree; you get a verdict, the minority view, and what the evidence cost.

## Pages / sections (single-page app is fine)
1. Hero: tagline, one-line explanation, two buttons: "Reality Check, $8" and "Full Reality Check, $25". Buttons follow the "buy" flow below.
2. How it works, three steps: (a) paste your page URL or pitch, (b) the router decides how much evidence your claim is worth (model consensus first, humans only when they beat the price), (c) you get a verdict page with per-claim yes/no, human votes, minority view, and the cost of the evidence.
3. Products: read from `GET /summary` -> `skus`. Show name, price, evidence standard, and the claims list (these are the yes/no questions we judge). Two products only: `reality_check` and `full_reality_check`.
4. Live company brain (dashboard): read from `GET /summary` every 10 s. Show: money (revenue, evidence cost, margin) as three big numbers; counts (jobs, humans answered, router bought vs declined); the two learning lines verbatim as text (swarm check verdict, and per-arm gains); recent jobs table (job_id short, sku, status, verdict + p, humans, router arm + reason truncated, revenue, cost). Each row links to `https://reality-check-0f80.onrender.com/verdict/{job_id}` (opens in new tab; that page already exists on the backend).
5. Footer: built at the Zero Human Company hackathon; Terac (humans), Stripe (payments), Replay QA (objective checks), Render (hosting).

## The buy flow (exact)
When the user clicks buy:
1. Show a small form: `input` (textarea, "your landing page copy, pitch, or URL", required), and for Full Reality Check an optional `extra_claims` (up to 8 lines, "what you claim your product does autonomously").
2. `POST https://reality-check-0f80.onrender.com/order` with JSON:
   `{"input": "<text>", "sku": "reality_check" | "full_reality_check", "extra_claims": ["..."]}` (omit extra_claims if empty).
   Response: `{"job_id": "abc123", "status": "pending_payment", "price_usd": 8.0, "pay_url": "https://buy.stripe.com/...?client_reference_id=abc123"}`.
3. Redirect the browser to `pay_url` (window.location). That is Stripe's hosted page. Do not embed Stripe.
4. Also show the user a "your result link" they can keep: `https://reality-check-0f80.onrender.com/verdict/{job_id}` and a status poller: `GET /order/{job_id}` returns `{"status":"pending_payment", ...}` until paid, then the full verdict JSON (`status` becomes `evaluating` / `awaiting_humans` / `settled`). Poll every 5 s and show status text.

If `pay_url` is null, show "payment link not configured" (do not fake it).

## Endpoints you may call (all GET unless noted, all JSON, base https://reality-check-0f80.onrender.com)
- `GET /summary` -> `{money:{revenue_usd,cost_usd,margin_usd}, counts:{jobs,by_status,humans,voi_bought,voi_declined}, learning:{swarm_check:{n_jobs,verdict,...}, arms:{name:{arm,n_settled,measured_gain,live,overturned_jobs}}}, skus:{sku:{price_usd,evidence_standard,claims:[]}}, pay_links:{reality_check:url,full_reality_check:url}, recent:[{job_id,status,verdict,p,n_humans,sku,voi:{buy,arm,reason},revenue_usd,evidence_cost_usd,summary}]}`
- `POST /order` (above). `GET /order/{job_id}`.
- `GET /judge/{job_id}` -> verdict JSON: `{job_id,status,verdict:"yes"|"no"|"undecided",p,confidence,agreement,n_evaluators,n_humans,summary,minority_view,claims:[{claim,verdict,p_internal,agreement,p_humans,n_humans,minority_view,lens,objective}],voi:{buy,arm,reason,net_value_usd,evidence_price_usd},revenue_usd,evidence_cost_usd,margin_usd}`
- `GET /skus`, `GET /ledger`, `GET /events?limit=50` (decision log: `[{at,kind,payload}]`, nice for a "what the company is doing" ticker).
Backend HTML pages you can link to (do not rebuild): `/verdict/{job_id}`, `/rate/{job_id}` (the human rating page), `/` (raw ops dashboard).

## Visual direction
Plain, confident, editorial. Black text on off-white, one accent color (deep green) for money and "yes", a muted red for "no". System font stack or a single serif for headings; no Inter, no emoji, no gradients, no stock illustrations. Big numbers for money. Tables, not cards, for the jobs list. It should read like a decision log from a company that knows what its evidence costs. Mobile first: people in the room will open this on phones from a QR code.

## Hard rules
- No backend, no Supabase, no auth, no localStorage of anything sensitive.
- All data from the base URL above; if a fetch fails show "backend unreachable" text, never mock data.
- Do not change the API contract; if something is missing, show it as missing.
