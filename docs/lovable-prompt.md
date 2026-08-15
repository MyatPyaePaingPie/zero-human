# Lovable build brief: Reality Check storefront

## What this is for

Lovable is building the public sales and transparency layer for Reality Check. The Python service
already owns orders, payment state, evidence routing, verdicts, and the ledger. This frontend has
two jobs only:

1. Turn a founder's page, URL, or pitch into a paid Reality Check order.
2. Prove the product's premise by showing the real company ledger and recent decisions live.

It is not an ops console, a replacement verdict page, or a second backend.

## Current status verified on 2026-08-15

- The backend is live at `https://reality-check-qhy9.onrender.com` and `GET /summary` returns real
  JSON with CORS enabled.
- The two public products are configured at $8 and $25 with live Stripe Payment Links.
- The live snapshot contained 18 jobs: 17 settled and one evaluating. It showed no human answers,
  $0 revenue, about $0.0024 in model evidence cost, and slightly negative margin. The page must make
  sparse early data look intentional, never replace it with demo data.
- The repository is on `main`; 28 backend tests pass. The storefront itself has not been built in
  this repository. This file is the handoff to Lovable.

## Why this prompt is shaped this way

Lovable's current guidance says to define the user, key action, real content, component boundaries,
visual direction, loading and error states, and backend behavior before building. It also says a
detailed visual brief lets Lovable build directly instead of falling back to generic design choices.
Those rules are applied below.

Sources: [Prompting best practices](https://docs.lovable.dev/prompting/prompting-one),
[How to build a real product](https://docs.lovable.dev/tips-tricks/from-idea-to-app), and
[Design guidance](https://docs.lovable.dev/features/design-guidance).

## How to use this

Start a blank Lovable project. Attach
[`reality-check-lovable-art-direction.png`](assets/reality-check-lovable-art-direction.png) and paste
everything below the line as the first Build mode prompt. The image controls visual hierarchy and
mood only. The written brief controls all copy, data, behavior, and accessibility.

---

# Build Reality Check

Build the complete, production-ready single-page storefront described below in one pass. Think
through the component and state model before coding, then implement and test it. Do not pause for
design questions because the design decisions are already specified. Ask only if a genuine blocker
makes the API contract impossible to implement.

## Product and user

Reality Check sells evidence-routing under uncertainty. It decides whether another model, a crowd,
or an expert is worth paying for before money gets attached to a claim.

The primary visitor is a founder or builder opening this page from a QR code on a phone. They have a
landing page, URL, or pitch and want one honest answer: will a stranger understand it? The key action
is submitting that material, creating an order, and continuing to Stripe's hosted Payment Link.

This site is also the proof. Its lower half exposes the actual money, evidence costs, routing
decisions, learning, and recent checks from the live backend.

## Non-negotiable architecture

This is a view layer only over an existing backend.

- Build a responsive React frontend using the project's normal Lovable stack and Tailwind.
- Use browser `fetch` directly against `https://reality-check-qhy9.onrender.com`.
- Do not create or connect Lovable Cloud, Supabase, a database, auth, storage, server functions, edge
  functions, API proxies, secrets, or a new backend.
- Do not build or embed checkout. Payment happens only at the `pay_url` returned by `POST /order`,
  which is a Stripe-hosted Payment Link.
- Do not use mock, sample, fallback, seeded, or invented product data anywhere, including charts,
  jobs, metrics, testimonials, timestamps, and verdicts.
- Do not store the submitted pitch or URL in localStorage, sessionStorage, cookies, analytics, or the
  page URL. Keep it only in component memory until it is sent to the backend.
- A public `job_id` may be put in the query string as `?job=<job_id>` so the status view survives the
  Stripe round trip. Store nothing else.
- Never alter or compensate for the API contract. Missing data renders as `Not available`.

## Art direction

Use the attached image as the visual reference for hierarchy, proportion, typography mood, paper
texture, color, rules, and the transition into the dark live-ledger section. Do not copy any metric,
row, timestamp, or claim from the image. Live API data and this written brief always win.

The visual idea is: an independent financial newspaper's markets page crossed with a transparent
research lab ledger. It should feel candid, expensive, slightly confrontational, and unusually
specific. It must not look like a generic AI-generated SaaS landing page.

Design tokens:

- Warm paper background: `#F3F0E8`
- Near-black ink: `#151714`
- Deep evidence green: `#174C38`
- Muted verdict red: `#9A3D36`
- Hairline rule: `#C9C4B8`
- Dark ledger surface: `#111411`
- Maximum content width: about `1440px`
- Square corners or at most `2px` radius
- Hairline borders, no decorative shadows
- Heading font: `Instrument Serif` if available through Google Fonts, with `Georgia` fallback
- UI and body font: `IBM Plex Sans`, with system sans fallback
- Monospace: `IBM Plex Mono`, used only for job IDs, status labels, and ledger numbers

Use a disciplined 12-column editorial grid on desktop and a single-column composition on mobile.
The hero headline is oversized, left-aligned, serif, and allowed to wrap across three deliberate
lines. The order composer sits to its right. Section rhythm comes from scale, rules, background
changes, and density, not boxes.

The only motion is a quiet live-status pulse and a brief numeric fade when refreshed data changes.
Honor `prefers-reduced-motion`.

Never use:

- Inter
- gradients, glow, glassmorphism, or blurred floating navigation
- bento grids or a grid of feature cards
- rounded pills, bubble buttons, or giant rounded containers
- stock photography, illustrations, 3D objects, decorative icons, or emoji
- testimonials, fake logos, social proof, invented charts, or invented metrics
- a centered hero, a hero eyebrow, or a giant empty first viewport
- purple, cyan, pastel SaaS colors, excessive shadows, or every section inside a card

## Page anatomy

### 1. Masthead

A slim horizontal masthead with a bottom rule.

- Left: `REALITY CHECK` as a typographic wordmark.
- Right: a small green dot, `LIVE API`, and `UPDATES EVERY 10 S`.
- On mobile, keep the wordmark and `LIVE API`; hide only the update cadence if space requires it.
- No conventional navigation bar. Add small anchor links only if they fit without competing with the
  primary action: `How it works` and `The company, live`.

### 2. Hero and order composer

Desktop: a 7/5 split. Mobile: headline first, composer immediately after it.

Exact hero copy:

`Pay $8. Find out if you're bullshitting yourself.`

Supporting copy:

`At least three real people read your page or pitch. You get a verdict, the minority view, and what the evidence cost.`

Do not add an eyebrow, badge, review score, trust-logo strip, or extra marketing paragraph.

The order composer is a thin-rule editorial form, not a floating rounded card.

- Heading: `Check your pitch or page`
- Product selector: two rectangular text tabs with an underline or filled ink state. Default to
  `Reality Check · $8`; second option is `Full Reality Check · $25`.
- Required textarea label: `Your page, pitch, or URL`
- Placeholder: `Paste the text, link, or draft you want checked.`
- Show a `0 / 20,000` character count.
- When Full Reality Check is selected, reveal an optional second textarea.
- Optional label: `Claims about what your product does autonomously`
- Helper: `One claim per line, up to 8.`
- Primary submit label: `Create my Reality Check`
- Beneath the button: `Payment continues on Stripe.`

Do not duplicate product CTAs elsewhere in the first viewport.

### 3. What happens to your claim

Heading: `What happens to your claim`

Render three numbered editorial columns divided by rules, not cards:

1. `Paste the thing`
   `Send the page, URL, or pitch you are about to act on.`
2. `We buy only useful evidence`
   `Models go first. Humans are added when the evidence standard or the value of being right requires them.`
3. `You get the receipts`
   `See the verdict, each claim, the minority view, and exactly what the evidence cost.`

On mobile, stack these as a ruled vertical sequence. Do not use icons.

### 4. Products

Do not use pricing cards. Use two broad comparison rows that feel like a newspaper rate sheet.
Read both products from `GET /summary` under `skus`, filtering to exactly `reality_check` and
`full_reality_check`. Convert snake case to display names.

Each row shows:

- product name
- live price
- evidence standard, displayed as `Human-backed` for `human_backed`
- the claims exactly as returned by the API

For Full Reality Check, group the visible meaning with small text labels: `clarity`, `demand`,
`autonomy`, and `economics`. Do not invent additional claims. Explain in one sentence:
`The full check tests whether people understand it, whether the demand case holds, what you claim is autonomous, and what the evidence cost.`

If a product is absent from the response, keep its row but show `Product unavailable` and disable
selection. Never fill in missing API data from the prompt.

### 5. The company, live

This is not a conventional admin dashboard. It is a public evidence ledger and the visual payoff of
the page. Use the dark ledger surface full width inside the page rhythm.

Heading: `The company, live`

Read `GET /summary` on first load and every 10 seconds. Keep prior successful values visible during
background refresh. Show a quiet update timestamp based on the successful client fetch time.

Money rail: three oversized tabular figures with labels `Revenue`, `Evidence cost`, and `Margin`.
Values come only from `money.revenue_usd`, `money.cost_usd`, and `money.margin_usd`. Format as USD
with two decimals. Revenue and positive margin use green. Evidence cost and negative margin use muted
red. Zero and unavailable values remain neutral.

Below the money rail, show compact counts from the API:

- Jobs: `counts.jobs`
- Human answers: `counts.humans`
- Evidence bought: `counts.voi_bought`
- Evidence declined: `counts.voi_declined`
- Status counts: entries from `counts.by_status`

Learning is a restrained text block, never a chart. Show:

- `Swarm check: <learning.swarm_check.verdict>` plus `n_jobs` and available Brier values.
- One row per entry in `learning.arms`, showing its `arm`, `n_settled`, `measured_gain`, `live`, and
  `overturned_jobs` values. Do not infer a gain or claim improvement when a value is null.

Recent checks is a semantic table, never cards. Columns:

- Job: first 8 characters of `job_id`, monospaced
- Product: `sku`
- Status
- Verdict: verdict plus `p` when present
- Humans: `n_humans`
- Route: `voi.arm` plus `bought` or `declined`; `Not available` when `voi` is null
- Reason: `voi.reason`, visually truncated to about 90 characters with full text in a title or
  accessible disclosure
- Revenue
- Evidence cost

Each row links to
`https://reality-check-qhy9.onrender.com/verdict/{job_id}` in a new tab with
`rel="noopener noreferrer"`.

On mobile, keep it a real table inside a clearly scrollable horizontal region. Do not transform rows
into cards. Keep Job, Status, and Verdict visible first.

When `recent` is empty, show one table-spanning row: `Waiting for the first check.`

### 6. Footer

One ruled footer line, no columns and no newsletter form.

Left: `Built at the Zero Human Company hackathon.`

Right: `Terac for humans · Stripe for payments · Replay QA for objective checks · Render for hosting`

## Exact data contract

Base URL:

`https://reality-check-qhy9.onrender.com`

Use only these endpoints:

### `GET /summary`

Use this shape as a type contract, not as data to seed:

```ts
type Summary = {
  money: {
    revenue_usd: number;
    cost_usd: number;
    margin_usd: number;
  };
  counts: {
    jobs: number;
    by_status: Record<string, number>;
    humans: number;
    voi_bought: number;
    voi_declined: number;
  };
  learning: {
    swarm_check: {
      n_jobs: number;
      verdict: string;
      ensemble_brier: number | null;
      best_single_brier: number | null;
      median_single_brier: number | null;
    };
    arms: Record<string, {
      arm: string;
      n_settled: number;
      measured_gain: number | null;
      live: boolean;
      overturned_jobs: number;
    }>;
  };
  skus: Record<string, {
    price_usd: number;
    evidence_standard: string;
    claims: string[];
  }>;
  recent: Array<{
    job_id: string;
    status: string;
    verdict: "yes" | "no" | "undecided";
    p: number;
    n_humans: number;
    sku: string | null;
    voi: null | {
      buy: boolean;
      arm: string | null;
      reason: string;
    };
    revenue_usd: number;
    evidence_cost_usd: number;
    summary: string;
  }>;
};
```

### `POST /order`

Send `Content-Type: application/json`.

For Reality Check:

```json
{
  "input": "<trimmed textarea value>",
  "sku": "reality_check"
}
```

For Full Reality Check:

```json
{
  "input": "<trimmed textarea value>",
  "sku": "full_reality_check",
  "extra_claims": ["<trimmed non-empty line>"]
}
```

Omit `extra_claims` when it is empty. Enforce a maximum of 8 non-empty lines in the client. Do not
send additional fields.

Response:

```json
{
  "job_id": "abc123",
  "status": "pending_payment",
  "price_usd": 8.0,
  "pay_url": "https://buy.stripe.com/...?client_reference_id=abc123"
}
```

### `GET /order/{job_id}`

Before payment, it returns `pending_payment` and may include `pay_url`. After payment it returns the
verdict shape without `pay_url`; `status` progresses through `evaluating` and `awaiting_humans` to
the terminal state `settled`, or ends in the terminal state `failed`.

## Order interaction and states

Do not open a modal. Keep the entire flow in the hero composer.

1. Validate a non-empty input and at most 20,000 characters. Validate Full Reality Check extra
   claims as at most 8 non-empty trimmed lines.
2. Disable the submit button while posting and label it `Creating your check...`.
3. POST the exact payload above.
4. On success, replace the form body with a compact order confirmation in the same ruled frame.
5. Use `history.replaceState` to add `?job=<job_id>` to the storefront URL. Do not put the submitted
   content in the URL or storage.
6. Show `Order <first 8 job characters> created`, the backend status, and a visible result URL:
   `https://reality-check-qhy9.onrender.com/verdict/{job_id}`.
7. Provide a `Copy result link` button in every order state.
8. Only while `status` is `pending_payment`, show a primary `Continue to secure payment` button. It
   uses `window.location.assign(pay_url)` in the same tab. Never embed Stripe.
9. For `evaluating` or `awaiting_humans`, remove all payment UI and show the current status plus an
   `Open result page` action. A paid order response does not contain `pay_url`; never treat that
   absence as a payment-configuration error and never retain a stale payment URL or button.
10. Start polling `GET /order/{job_id}` every 5 seconds while the confirmation is visible. Stop when
   the job reaches either terminal status, `settled` or `failed`, when the component unmounts, or
   when the job ID changes.
11. If the page loads with a valid `?job=<job_id>`, restore the confirmation and polling state by
    fetching that order. This makes returning from Stripe work without browser storage.
12. When settled, show `Your verdict is ready` and make `Open verdict` the primary action.
13. When failed, stop polling and show `This check failed before a verdict was produced.` Provide
    `Open result page` and `Start a new check` actions. Do not reuse the old input automatically.
14. If a query-string job returns 404, show `Order not found` with a `Start a new check` action that
    clears only the `job` query parameter and restores the form.

If a `pending_payment` response has a null or missing `pay_url`, show exactly
`Payment link not configured` and do not render a fake or disabled Stripe URL. This rule applies only
to `pending_payment`; later statuses are already paid and are not expected to contain `pay_url`.

For a POST error, preserve the user's input in component memory and show the API's safe message when
available, otherwise `We couldn't create your check. Try again.`

## Loading, empty, error, and accessibility behavior

- Initial summary load: show the page structure with `Loading live data...`, never placeholder
  numbers or skeleton values that resemble data.
- Summary failure: show `Backend unreachable` inside the live section with a `Retry` text button.
  Keep the storefront explanation and order form usable because order submission has its own error
  handling.
- If a successful summary response specifically omits one of the two public SKU keys, mark that
  product unavailable and disable it. If the summary request itself failed, do not infer that the
  SKU is unavailable; leave order submission available and let `POST /order` return the truth.
- Background refresh failure after prior success: keep the last successful values and show
  `Live update delayed` with the last successful client timestamp.
- Initial order-status fetch failure other than 404: show `We couldn't load this order.` with `Retry`
  and `Start a new check` actions.
- Order polling failure after at least one successful status: preserve the last successful status,
  result link, and allowed actions; show `Status update delayed` and a `Retry now` action. Continue
  bounded 5-second retries without duplicating timers. Clear that warning on the next successful
  response.
- Missing or null field: show `Not available`; never coerce null to zero.
- Verdict colors: yes is green, no is muted red, undecided is neutral. Always pair color with text.
- Use semantic headings, labels, buttons, table elements, and live regions for order status and fetch
  errors.
- All controls must be keyboard reachable with visible ink-colored focus styles.
- Minimum touch target is 44px. Body text is at least 16px on mobile.
- Respect contrast, reduced motion, long API strings, narrow screens, and browser zoom to 200 percent.

## Component and code boundaries

Keep the implementation small and legible. A suitable structure is:

- `api` module for the base URL, fetch helper, response checks, and request functions
- `useSummary` hook for initial fetch, 10-second refresh, cleanup, and stale-data behavior
- `useOrderStatus` hook for query-string restoration and 5-second polling
- `Masthead`
- `OrderComposer`
- `ProcessRail`
- `ProductRows`
- `LiveLedger`
- `RecentChecksTable`
- `Footer`

Do not put the whole page in one component. Do not add packages for state management, charts,
payments, forms, icons, or data fetching when browser APIs and React state are sufficient.

## Final verification before you stop

Run the app and inspect it in Lovable's browser. Fix failures before reporting completion.

Verify all of these:

- desktop around 1440px wide
- mobile around 390px wide
- no horizontal page overflow; only the recent table may scroll horizontally
- first viewport clearly communicates the offer and exposes the usable order composer
- summary loads from the live backend with no mock data in source or UI
- selecting Full Reality Check reveals and submits `extra_claims`
- the POST body contains only `input`, `sku`, and optional `extra_claims`
- a created order shows its result link before payment navigation
- payment action uses the returned `pay_url`
- null `pay_url`, unreachable backend, empty recent jobs, null VOI, and null learning values render
  honestly
- `?job=<job_id>` restores status polling without storage
- payment UI appears only for `pending_payment`, and paid responses do not require `pay_url`
- `settled` and `failed` both stop polling and render distinct terminal states
- initial and background order-status failures preserve honest recovery actions
- intervals and in-flight requests are cleaned up
- every interactive element works by keyboard and has a visible focus state
- there are no console errors
- there is no Supabase, Lovable Cloud, auth, backend, edge function, checkout embed, fake data,
  gradient, bento grid, card soup, pill UI, emoji, stock art, or Inter

Do not add features or copy beyond this brief. The result should feel like the attached art direction
made real with honest live data.
