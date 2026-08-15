---
type: research
status: active
created: 2026-08-15
---

# augur reconnaissance memo for the judgment/VOI hackathon (2026-08-15)

Repo: `/Users/slowember/Documents/Vaults/CodingVault/augur` (main, 121 commits, 2026-05-19 to 2026-08-10, 284 pytest tests). Read-only recon; nothing modified.

Headline: augur has **zero value-of-information machinery** (grep for VOI / expected_loss / oracle / human-in-the-loop returns nothing but comments). What it has is a mature, hard-won *skepticism* toolkit: probability + confidence schema, Brier-vs-crowd scoring, a fee-aware Kelly gate that fails closed, a hybrid Thompson/UCB1 bandit over "arms", a majority-vote consensus with a dissent threshold, a tiered LLM router with cost logging + provider bakeoff, and (in `augur/wide_edge`) an "autonomous company loop" skeleton with role-tagged decision logs and a paper AgentPay ledger that ran exactly once on synthetic fixtures and then stalled. The reusable part is ~600 lines of pure-Python dataclass math with no DB dependency; the rest is SQLite/venue/launchd plumbing you should not drag in.

---

## 1. Architecture map

### Package layout (`augur/`)

| module | what it does | key symbols |
|---|---|---|
| `core/brier.py` (67 l) | Brier score, crowd delta, decile calibration | `brier(p,y)=(p-y)^2`, `brier_score`, `brier_delta = crowd_brier - strategy_brier`, `calibration_deciles`, `max_calibration_deviation` |
| `core/kelly.py` (114 l) | sizing + the real-money gate | `breakeven_win_rate`, `kelly_fraction`, `size_position -> SizeDecision(size_pct, method, reason)` |
| `core/bandit.py` (222 l) | hybrid bandit over arms | `Arm(alpha,beta,ucb_n,ucb_sum,status)`, `allocate(arms, rng, policy) -> Allocation`, `update_posterior(arm, beat_crowd, reward)`, `thompson_sample`, `ucb1_scores`, `epsilon_greedy_scores` |
| `core/consensus.py` (115 l) | multi-voter aggregation, dissent-triggered skip | `Vote(hypothesis_id, forecast)`, `evaluate(votes) -> ConsensusVerdict(side, agreed_p, agreed_confidence, voters_for, voters_against, voters_skip, dissent_score, rationale)`, `DISSENT_THRESHOLD=0.20` |
| `core/recompute_side.py` (85 l) | deterministic decision from (p, market_p, confidence); outlier guard | `recompute_side`, `EDGE_FLOOR=0.05`, `EDGE_CAP=0.50`, `CONFIDENCE_FLOOR=0.55`, `harden_payload` |
| `core/lifecycle.py` (82 l) | hypothesis state machine with confidence updates | `apply_evidence`: supports `c += (1-c)*0.25`, refutes `c -= c*0.30`; testing->supported at c>=0.8, for>=3, ratio>=3:1; testing->refuted at c<0.2, against>=2; graduate/kill need "human approval" (never built) |
| `core/scoring.py` (30 l) | canonical dedupe SQL view (one row per market) | `LATEST_PER_MARKET`, `LIVE`, `TRADED` |
| `core/selection.py` | market selection/junk filter, "beatable" domain classifier | `classify`, `select` |
| `core/fitness_bridge.py` | shim to crystal-os `NodeFitnessTracker` (XP/level/consensus_rate); degrades to a stub | `FitnessBridge.record(hyp, beat_crowd, strategy_brier)` |
| `core/arm_storage.py` | SQLite impl of armature's `RuntimeStorageProtocol` (per-user/agent arm posteriors, decisions, reward updates) | `SQLiteRuntimeStorage` |
| `core/weather_optimizer.py` | armature Thompson bandit picking per-city spread inflation; reward = beat_crowd binary | `select_config`, `reward_config` |
| `core/db.py` + `schema.sql` | SQLite (`_meta/augur.db`); tables: hypotheses, experiments, strategy_state, decisions, station_bias, strategy_provider_state, resolutions, bandit_ticks, prompt_cache_meta, halts | `cursor`, `fetch_all`, `upsert_hypothesis` |
| `llm/schema.py` | Pydantic I/O contract | `Forecast(p, confidence, reasoning, refuted_by, side, forecast_mean)`, `MarketSummary` |
| `llm/sanitize.py` | prompt-injection scrub of attacker text | `sanitize_market_text` (strips URLs, fences, "ignore previous", role prefixes, `<|..|>`; 4000 char cap) |
| `llm/router.py` (175 l) | tier-ordered provider fallback + cost log | `Router.call` (Forecast), `Router.generate` (arbitrary JSON schema), `DEFAULT_ORDER{cheap,standard,escalation}`, env override `AUGUR_PROVIDER_ORDER_<TIER>` |
| `llm/providers/*` (1685 l) | anthropic_sdk, bedrock_api, gemini_api/cli, codex_cli, groq, groq_ensemble, ollama_http/ensemble, openai_api | `LLMProvider.forecast/available/generate`, `ProviderResult(forecast, provider, model, input_tokens, output_tokens, cost_usd_estimate, latency_ms)`, `GenerateResult(data,...)` |
| `llm/providers/ensemble.py` | N members -> median p, agreement-scaled confidence | `EnsembleProvider.forecast` |
| `strategies/` | H001 naive LLM, H001c self-consistency (median of 3, min conf), H002 base rate, H003 calibration arb, H004 news, H005 sentiment, H006 slow-CLOB mean reversion, H007 weather | `Strategy.forecast_with_provider`, `registry.ALL` |
| `runtime/tick.py` (818 l) | 5-min loop: halts, loss caps, selection, votes, consensus, bandit alloc, sizing, submit, provider bakeoff pass, weather pass | `tick`, `_rolling_calibration`, `_collect_votes`, `_provider_bakeoff_pass` |
| `runtime/resolve.py` | hourly settle: paper PnL, posterior rollups (per hypothesis and per (hypothesis, provider)), lifecycle | `_update_posteriors`, `_update_provider_posteriors`, `_apply_lifecycle` |
| `runtime/watchdog.py` | independent 60s guard: daily 5% / weekly 10% loss caps, 10% exposure cap, reconciliation, halts table | `watchdog_once` |
| `runtime/notify_resolved.py` | macOS notification when paper bets settle (the only "human in loop") | |
| `tools/` | replay bootstrap, dashboard, adversary packet, experiment_runner, edge_scan, kalshi_efficiency, provider_bakeoff_report, postmortem | `provider_bakeoff_report.report` |
| `venues/` | manifold, kalshi (RSA-PSS), base `Market` | |
| `arb/` | Kalshi settlement-gap detector, IEM | |
| `wide_edge/` (643 l) | Phase 0 "autonomous company" pilot, see section 3 | `models`, `scoring`, `registry`, `pilot`, `store` |

### Sibling harnesses (top level, own SQLite + JSON mirror each)
- `narrative_alpha/` (daily launchd): AI-narrative contrarian stock signal; `arms.py` plugs into `augur.core.bandit` verbatim; block-bootstrap-by-month CIs; options model; auto LLM-judge flag arm (`autoflag.py`).
- `maker_alpha/` (hourly): Polymarket maker viability, pessimistic FIFO queue sim (`queuesim.py`), 30-day forward gate. Verdict: straddles zero.
- `tactical_alpha/` (hourly): intraday 15m crypto book; where the +5162% fake-sizing bug was found.
- `atlas/`: Phoenicia "node vs route death" post-mortem lens.
- `crypto/`, `stocks/`: one-off backtests.

### Data flow (core loop)
venue scan -> `selection.select` -> per-strategy `Forecast` via `Router` -> `consensus.evaluate(votes)` -> `bandit.allocate(arms)` gives per-arm bankroll share -> `size_position` gate -> paper/live submit -> `decisions` row -> hourly `resolve` computes brier/crowd_brier/pnl -> `_update_posteriors` rebuilds Beta(1+wins, 1+losses) per arm from the deduped view -> `lifecycle.apply_evidence`. LLM cost per call goes to `prompt_cache_meta`.

### launchd jobs (`plists/`)
augur-tick 300s, augur-watchdog 60s, augur-resolve 3600s, augur-experiments (calendar), augur-dashboard, augur-caffeinate, maker-alpha hourly, narrative-alpha daily, tactical-alpha hourly. Runner: `scripts/augur-runner.sh` (keychain secrets).

---

## 2. Machinery inventory, with code shape

### Probability / confidence representation
`Forecast` = `p in [0,1]` (P(YES)), `confidence in [0,1]` (self-reported), `reasoning`, `refuted_by: list[str]` (counter-evidence considered), `side in {yes,no,skip}` (always overwritten by `recompute_side`), `extra="forbid"`. Confidence is treated as a *gate input*, never as a probability: `< 0.55 -> skip`.

### Aggregation of multiple evaluators (the closest thing to an "internal evaluator market")
- `consensus.evaluate`: majority on side; `agreed_p` = mean p of majority voters; `dissent_score = |mean_p_for - mean_p_against|`; **skip if voters_against and dissent < 0.20** (note: augur skips on LOW numeric dissent, i.e. the two camps are close in p, meaning "no clear edge"; a tie in vote count also skips). Not stake-weighted; no incentives.
- `EnsembleProvider`: `median_p`, `agreement = max(above,below)/n` relative to market_p, `adj_conf = mean_conf * agreement`; raises if fewer than `min_models` respond.
- `H001c`: median of N samples, confidence = min of N.
- None of these have a stake, payout, or scoring rule per voter. Per-voter scoring exists only at the arm level (Beta posterior from beat_crowd).

### Calibration / scoring
`brier`, `brier_delta`, `calibration_deciles`; edge doctrine `crowd_brier - strategy_brier >= 0.010`. Reward to bandit is `beat_crowd = brier < crowd_brier` (binary), optional `reward in [0,1]`. `narrative_alpha.arms._norm(r, scale) = clip(0.5 + r/(2*scale))` maps returns to UCB rewards.

### Expected value / breakeven / thresholds
- `breakeven_win_rate(market_p, fee=0.07)`: payout `(1-p)/p`, fee `f*p*(1-p)`, `WR = 1/(1+net_win)`.
- `kelly_fraction(strategy_p, market_p)`: `edge = p_s*payout - (1-p_s)`, `kelly = edge/payout`, sign = side.
- `size_position` gate order: confidence<0.55 -> zero; |p - market_p|<0.05 -> zero; below fee breakeven -> zero; **Kelly unlocked only if** `kelly_unlocked and rolling_brier<0.20 and n_resolved>=200 and rolling_edge>=0.01` (rolling_edge None fails closed); else fixed 2%; when open, `0.25 * |kelly|` capped 10%. Hardwired `kelly_unlocked=False` everywhere in production.
- Loss caps: daily 5%, weekly 10%, exposure 10% (tick + watchdog both enforce).

### Bandit across arms
`allocate`: pick policy by weights {thompson .60, ucb1 .20, eps-greedy .10, uniform .10}; scores -> top gets 50%, above-median share 40%, `testing` arms floor 5%, killed/refuted 0, normalize. `update_posterior` = Beta-Bernoulli + UCB running mean. narrative_alpha's `_expected_allocation` averages 2000 seeded draws because one draw is a coin flip (that was a live bug). Per-(strategy, provider) posteriors exist in `strategy_provider_state`.

### Settlement / resolution
`resolve._settle_pending` pulls venue outcome, `_paper_pnl` nets fees, sets brier + crowd_brier; `wide_edge.scoring.settle_observation` generalizes to any `edge_metric in {brier, resale_pnl}` with `net_edge = organism_edge - simulated_burn` and `beat_baseline`. Settlement is only allowed after a pre-registered resolution window (`Observation.is_settleable(as_of)`); forward leakage check `validate_forward` rejects forbidden post-observation fields.

### Statistical clearance
`wide_edge.scoring.block_bootstrap_ci` (blocks by month, 600 iters, seeded `random.Random`), `domain_stats[...]["cleared"] = n>=30 and avg_net>0 and ci_lo>0`. narrative `harness._block_boot` same idea, plus a sign-aware `powered` flag (CI entirely on the thesis side).

### Evidence handling
`Forecast.refuted_by` list; `sanitize_market_text` for hostile input; `wide_edge.models.DecisionLogEntry(observation_id, domain_id, role, ts, action, detail)` for role-tagged evidence trail (scout/forecaster/adversary/treasurer/scorer/archivist); `stable_hash` of raw payload.

### LLM usage, router, bakeoff
- Tiers cheap/standard/escalation, first-available-provider-wins with fallback (not quality-routed). Cost/tokens/latency logged per call.
- `Router.generate(response_schema=...)` for arbitrary structured JSON, provider-agnostic.
- Provider bakeoff: `tick._provider_bakeoff_pass` runs the SAME market+strategy across `PROVIDER_BAKEOFF_PROVIDERS`, logs decisions tagged `provider_bakeoff`, and `tools/provider_bakeoff_report.report` computes per-provider `avg_edge`, `beat_rate`, observed prompt cost, and **`edge_per_dollar = avg_edge / cost_usd`**. That is the seed of a "provider cost/quality" ledger. Latency is captured per call but not aggregated.

### Uncertainty concepts
Beta posteriors per arm; agreement factor; dissent score; edge cap ("beyond 0.50 we don't trust ourselves"); confidence floors; fail-closed on unmeasured edge; forward-only n>=30 gate.

### Human in the loop / agent to agent / incentives / market maker
- Human: only a macOS notification (`notify_resolved`) and two lifecycle transitions that say "human approval" but were never wired. No human evaluation, no Terac-like purchase.
- Agent to agent: only wide_edge role labels in a decision log; no messaging or A2A protocol was built. `fitness_bridge` shim to crystal-os (XP, clone/prune eligibility) is the nearest thing to inter-agent reputation.
- Incentives: none. Voters are not staked; the only "payment" is Beta posterior mass.
- Market maker: `maker_alpha/queuesim.py` (pessimistic FIFO fill sim, markouts) and Kalshi fee math. Not relevant to judgment pricing except as a reminder that spread eats edges.

---

## 3. wide_edge / autonomous company loop / AgentPay: what happened

**Commissioned** (2026-06-29, `_meta/commissions/active/2026-06-29-wide-edge-pilot.md`, still "active"): PersistOS "organism" whose fitness is money net of compute burn. Roles: coordinator, scout, forecaster, treasurer, scorer, adversary, archivist, spawned dynamically on crystal-os with a **coordination null hypothesis** (organism must beat a fixed pipeline on the same data, forward-honest, n>=30, block-bootstrap). Domains must pre-register a scoring contract (crowd source, resolution event, forbidden post-observation fields, burn model, cash-in model, failure modes) or they are out of scope. AgentPay folded in (`a1731e0`) as the policy/identity layer vocabulary: cost agent (spend/velocity limits, freeze, kill switch), revenue agent (`deploy`/`return`, outstanding capital, ROI), transaction kinds spend/return; Phase 0 offline/testnet only. Two-track loop added 2026-07-01 (Aria's consulting = ground-truth priors; augur = hypothesis discovery).

**Built** (2026-06-30, `550b69e`, chronicle `_meta/chronicles/2026/2026-06-30-wide-edge-pilot-demo-runner.md`): `augur/wide_edge/` = `DomainContract.validate`, `Observation.validate_forward/is_settleable`, `ForecastDecision`, `LedgerEntry(agent_type cost|revenue, kind spend|deploy|return)`, `DecisionLogEntry`, `Settlement`, `settle_observation`, `block_bootstrap_ci`, `domain_stats`, seed contracts (secondary resale, domain resale, clean-deadline events), and `pilot.run_demo` which manufactures synthetic fixtures, writes `wide_edge/wide_edge_pilot.json` and `_meta/reports/wide-edge-demo/GATE.md` (verdict GO on fixtures, "proves the loop runs, not edge"). Bandit allocation over domains uses `augur.core.bandit.allocate`. 6 unit tests. `--demo` is the ONLY implemented mode (`parser.error("only --demo is implemented")`).

**Why it stalled**: nothing after 06-30 touched it. Next day the session pivoted to four market research maps and the two-track commission; 07-06 opened maker_alpha; 07-16 provider bakeoff; 08-10 tactical_alpha. Concrete blockers named in the plan/chronicle: no live Apify adapters, crystal-os integration deferred ("too much dependency surface before the scoring contract exists"), agent-playground not pulled, AgentPay repo not local (not under CodingVault; only referenced by commit sha `e481407` and hardening gaps: KMS signing, reconciliation worker, drawdown tracking, rate limiting). The organism roles are string labels in a log, not agents. The "coordination null" was a `avg_org > avg_base` comparison on fixtures where baseline edge is hardcoded 0.0. Honest reading: it was a spec-driven skeleton that had no data source, no money rail, and no coordination substrate, so it had nothing to iterate on and got outcompeted by measurable market experiments.

Also relevant prior art: `_meta/dreams/invented-edge-2026-06-25.md` (three theses incl. "The Lawyer": LLM reads resolution fine print; adversary noted "for novel quirks there's no oracle to pre-verify, you only learn at settlement"), and `_meta/reports/edge-scorecard-2026-08-10.md` (11 routes, 8 dead, zero cleared, zero dollars traded).

---

## 4. Honest verdict on the three questions

### (a) Can judgment purchasing be modeled with augur's VOI/EV/Kelly machinery elegantly?
Partly, and only as *concept plus a few pure functions*. augur has no VOI. Its EV machinery is binary-market specific (payout `(1-p)/p`, Kalshi fee); the buyer rule `buy iff E[loss_without] > E[loss_with] + cost` is a decision-theoretic quantity augur never computes. What maps cleanly:
- Brier/loss as the "expected loss" currency: `brier.py` (67 lines, zero deps) gives you `brier`, `brier_delta`, decile calibration. E[loss_without] can be `E[(p_internal - y)^2]` under the buyer's own belief; E[loss_with] under an evidence-quality model. You will write the VOI expression yourself (~30 lines).
- The gate *shape* of `size_position` (fail closed, confidence floor, edge floor, min-n unlock, capped fraction) is a good template for "how much budget to spend on judgment this decision" but its formulas are market-specific; lift the structure, rewrite the body.
- `consensus.evaluate` and `EnsembleProvider` aggregation give you `agreed_p`, `agreement`, `dissent_score` for free; dissent is the natural trigger for "buy external judgment".
- `lifecycle.apply_evidence` is a cheap confidence-update rule for a "seller reputation" or "domain trust" state.
Verdict: reusable concept + ~250 lines of liftable pure code (`brier.py`, `consensus.py`, `recompute_side.py`, `lifecycle.py`, `kelly.py` minus fee math). No DB, no venues needed; they import only `augur.llm.schema.Forecast` (a 20-line Pydantic model you can inline).

### (b) Does augur make "internal evaluator market -> disagreement -> buy human judgment -> human = settlement oracle" nearly free?
It makes the *disagreement detector* and the *settlement scorer* nearly free; it does NOT make the market or the oracle plumbing free.
- Free: N evaluators emit `Forecast(p, confidence)`; `consensus.evaluate` -> `dissent_score`, or `EnsembleProvider`-style `agreement`; threshold triggers purchase. Human verdict `y` (or a human `p_h`) settles each evaluator via `brier`; `bandit.update_posterior(arm, beat_crowd=brier_i < brier_consensus)` maintains per-evaluator Beta reputation; `allocate` reweights evaluators for next time. That is a working "evaluator reputation market" in ~150 lines and it is exactly the augur pattern (arm = evaluator, crowd = consensus).
- Not free / not present: staking, payouts, incentive-compatible scoring rule (augur never pays voters), the human panel adapter (Terac), the settlement semantics when the human answer is itself a probability rather than a 0/1 outcome (augur only settles on binary outcomes; wide_edge adds abs-error for continuous). Also beware: augur's own history says the crowd/human "oracle" can be wrong and the model can be "reliability lipstick on a losing model"; you need the human result to be independently better than the internal consensus for it to be a settlement oracle, and augur has no machinery to test that except `brier_delta` over time.
Verdict: not overcomplication if you copy the ~3 pure modules; overcomplication if you import augur's runtime/DB/hypothesis tables. Build a fresh 500-line service and vendor the functions.

### (c) Could augur be the economic spine (providers with cost/quality/latency histories, bandit routing)?
Concept yes, code partially, live spine no.
- Router routes by fixed tier order, not by learned quality; there is no cost/quality/latency-aware routing. `ProviderResult` already carries `cost_usd_estimate`, `latency_ms`, tokens; `strategy_provider_state` keeps Beta posteriors per (strategy, provider); `provider_bakeoff_report` computes `edge_per_dollar`. So the *ledger fields* exist and the *bandit* exists but nobody has wired `allocate` to provider choice. Wiring is ~60 lines: arm_id = provider (or evidence strategy: cheap-model / ensemble / browser-QA / human panel), reward = normalized (loss reduction per dollar), `allocate` picks, `update_posterior` on settlement.
- Do not use `Router` itself (imports `augur.core.db`, providers need keys and each is 100-230 lines). Use its `LLMProvider` ABC shape and `GenerateResult` dataclass as the provider interface.
Verdict: reusable concept + `bandit.py` verbatim (222 lines, stdlib only) + the `ProviderResult` field list. Everything else is not worth it for an 8-hour build.

---

## 5. Hard lessons from augur that will bite a judgment-pricing service

1. **Dedupe or die.** Counting re-logged rows made n 165x too big and lit a fake "cleared for real money" badge (`scoring.LATEST_PER_MARKET`, readiness report 2026-06-12). In a judgment service: one decision that gets re-evaluated N times is one sample. Key every settlement by decision_id.
2. **Own-accuracy gate without a baseline is lipstick.** Model Brier 0.161 < 0.20 cleared the gate while being worse than parroting the market (edge -0.044). Fixed by requiring `rolling_edge >= MIN_EDGE` and failing closed on None (`3f2248d`). For you: any "our judgment is good" claim must be relative to the buyer's own free prior; VOI must be measured as loss reduction vs doing nothing, not absolute accuracy.
3. **Confidence was anti-predictive.** Post-fix weather scan: traded (high-confidence) markets had WORSE edge than skipped ones (-0.032 vs -0.017). Self-reported LLM confidence is not calibrated; never let it price a purchase without a calibration curve (`calibration_deciles`).
4. **Sizing artifacts manufacture edges.** Forced-full-investment made losing trades a +5162% book; fixed slot counts flip signs; uncapped stacking made +1105 on a 100 bankroll. Any budget/exposure constant that changes the sign of your result is a free parameter that must be derived from data (target_slots = p90 concurrency lesson, `251f8a3`). For a per-decision budget: derive from measured loss distribution, do not hand-pick.
5. **One bandit draw is a coin flip.** Displayed allocation had the negative-return foil on top at 47.6% (a 2% tail draw). Report the expected allocation over seeded draws (`narrative_alpha.arms._expected_allocation`), and seed everything.
6. **Sign-blind gates.** `powered` fired on any significance, including thesis-refuting. A "human judgment helped" gate must check the direction of the effect.
7. **Backdate/leakage.** `observed_at` recorded but never enforced -> 53% of notes would have settled instantly. Stamp observation time at capture, forbid post-observation fields (`Observation.validate_forward` pattern), and never let the human answer leak into the internal evaluators' inputs before they commit.
8. **Hand-rolled bootstrap collapsed** to `[mean, mean]` on power-of-2 n; use `random.Random` seeded (`kalshi_efficiency._boot_ci`).
9. **Spread/fee eats everything.** Every taker edge died to the 7% fee and 1-2c spread; the maker sim straddled zero. Your cost side (Terac human panel price, model tokens, latency) must be in the same units as the loss reduction, and the purchase rule must clear it with margin, not at breakeven.
10. **Node death vs route death.** Atlas showed augur's failures were forecast quality, not latency. Do not blame the panel's slowness when the internal evaluators are just wrong; measure both.
11. **Free-tier and heat.** Local Ollama overheated the laptop; Groq free tier is 30 RPM. Cloud cheap-tier default; cap calls per run (`NARRATIVE_AUTOFLAG_MAX_JUDGED` pattern).
12. **Fixtures that pass are not evidence.** wide_edge's GO gate on synthetic data was labelled honestly and still went nowhere. If the demo settles on human labels you invented, say so in the verdict payload.

---

## 6. Ranked shortlist: what to lift (fresh ~500-line service, no DB)

| # | lift | from | why | est. |
|---|---|---|---|---|
| 1 | `bandit.py` verbatim (`Arm`, `allocate`, `update_posterior`, plus `_expected_allocation` from `narrative_alpha/arms.py`) | `augur/core/bandit.py`, `narrative_alpha/arms.py` | evaluator reputation + evidence-strategy routing (arm = evaluator or provider; reward = loss reduction per $) | 15 min copy + 30 min wire |
| 2 | `consensus.evaluate` + `EnsembleProvider` aggregation math (median p, agreement, dissent) | `augur/core/consensus.py`, `augur/llm/providers/ensemble.py` L100-125 | the "internal evaluators disagree -> buy" trigger; returns verdict, agreement, minority voters out of the box | 20 min (inline `Forecast`) |
| 3 | `brier.py` (+ `wide_edge/scoring.settle_observation`, `block_bootstrap_ci`, `domain_stats` gate) | `augur/core/brier.py`, `augur/wide_edge/scoring.py` | settlement scoring vs human oracle, calibration deciles, honest CI and n>=30 clearance | 15 min |
| 4 | Gate skeleton of `size_position` + `recompute_side` (confidence floor, edge floor, fail-closed unlock, capped fraction), rewritten as `should_buy_judgment(p_internal, agreement, cost, budget, n_settled, rolling_edge)` | `augur/core/kelly.py`, `augur/core/recompute_side.py` | encodes the fail-closed discipline; you write the VOI body: `buy iff E_loss_without - E_loss_with > cost` | 30-45 min |
| 5 | Provider/evidence ledger shape: `ProviderResult/GenerateResult` fields (provider, model, tokens, cost_usd_estimate, latency_ms) + `provider_bakeoff_report`'s `edge_per_dollar` metric + `LedgerEntry`/`DecisionLogEntry` dataclasses | `augur/llm/providers/base.py`, `augur/tools/provider_bakeoff_report.py`, `augur/wide_edge/models.py` | cost/quality/latency history per evidence source; role-tagged evidence trail for the returned verdict payload | 20 min |

Honourable mentions: `sanitize_market_text` (untrusted buyer text into evaluators, 5 min), `lifecycle.apply_evidence` (seller/domain trust state, 5 min), `Observation.validate_forward` (leakage guard on human answers, 10 min).

Do NOT lift: `Router`/providers (DB import, keys), `runtime/*`, `db.py`/schema, venues, `arm_storage` (armature protocol), `fitness_bridge` (crystal-os), anything under `_meta/`.
