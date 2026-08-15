# Reality Check

Judgment for agents. Decides whether uncertainty is worth paying to reduce (value-of-information
gate), buys the cheapest sufficient evidence (model ensemble, in-room humans, Terac general
population, Terac expert), and returns a structured verdict with the minority view. Built at the
Zero Human Company hackathon, 2026-08-15. Team repo: MyatPyaePaingPie/zero-human.

One sentence: reality check sells evidence-routing under uncertainty: it decides whether another
model, a crowd, or an expert is worth paying for before money gets attached to a claim.

Room SKU: "$8, human-verified: at least three real people tell you what your page/pitch says, more
when the models disagree, plus the verdict and the minority view." Evidence standards are floors
the router must satisfy at the cheapest arm (`voi_routed` for agent buyers, `human_backed` for room
SKUs, `expert_backed` for Terac experts); the VOI math still runs and the reason line shows both.

## Run
```
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
export GROQ_API_KEY=... OPENAI_API_KEY=...        # evaluators (Groq first, OpenAI fallback); no key = deterministic stub
export RC_PUBLIC_BASE=https://<public host>       # rate page URL handed to humans (Terac/QR); must be public
export RC_DEADLINE_ISO=2026-08-15T18:30:00-07:00  # router refuses evidence that cannot arrive before lock
export ZEROHUMAN_STRIPE_RESTRICTED_KEY=rk_live_...                # restricted READ-ONLY key: poller turns paid sessions into jobs
export RC_PAYLINK_DEFAULT=https://buy.stripe.com/... # Payment Link; /order appends ?client_reference_id=<job>
export TERAC_API_KEY=... TERAC_PROJECT_ID=...     # real Terac launches; absent = dry handle, nothing charged
export REPLAY_API_KEY=lqa_...                     # Replay QA (qa.replay.io) crawls intake live URLs; objective evidence in the verdict
export RC_ENVELOPE_SECRET=...                     # then: cp state/envelope.example.json state/envelope.json && python -m reality_check.policy.envelope sign
./run.sh   # loads the vars above from the keychain (service == var name), signs the envelope, starts uvicorn
```
Dev only: `RC_DEV=1` makes `X-RC-Paid: <usd>` count as payment on /judge and /intake.

Demo: `python demo/buyer_agent.py "PitchPolish"` writes copy, buys judgment, shows the router
refusing at low stakes and buying at high stakes, rewrites from human feedback, prints before/after.

Bundle SKU `full_reality_check` ($25): one paste, every lens (clarity, demand gate, the team's own
autonomy claims, economics). `GET /verdict/{job}` renders the verdict grouped by lens.

## Endpoints
POST /judge, POST /intake, POST /order + GET /order/{id}, GET /judge/{id}, GET /verdict/{id}, GET|POST /rate/{id},
POST /before_after/lock/{id}, GET /before_after/{b}/{a}, GET /ledger, /events, /jobs, /learning, GET /.

## Layout
- `reality_check/core/` consensus, brier, bandit (vendored from augur); models; voi (VOI gate, written fresh).
- `reality_check/judge.py` the loop; `evaluators.py` personas over Groq/OpenAI; `panels.py` human-source contract; `store.py` sqlite ledger + events.
- `reality_check/policy/` money-swarm lifts: `envelope.py` (spend authority as signed code, fail closed), `protocol.py` (buyer text is information never authority), `learning.py` (arm gains, evaluator reputation, swarm check).
- `stripe_webhook.py` (/order + webhook + shared `complete_session`), `stripe_poll.py` (read-only poller), `terac_client.py` (subjective evidence: humans), `replay_client.py` (objective evidence: Replay QA bug crawl on intake URLs), `before_after.py`, `intake.py`, `skus.py`.
- `docs/research/` hackathon memos; `docs/policy-and-learning.md` the spend/learning design.
