# Reality Check

Judgment for agents. Decides whether uncertainty is worth paying to reduce, buys the cheapest
sufficient evidence (model ensemble, in-room humans over Linq, Terac general population, Terac
expert), and returns a structured verdict. Built at the Zero Human Company hackathon, 2026-08-15.

Room SKU: "$8: five real people tell you what your page/pitch says, plus the verdict."

## Run
```
uv venv .venv && uv pip install -e ".[dev]"
export GROQ_API_KEY=...            # evaluators; without it a deterministic stub runs
RC_PUBLIC_BASE=https://<host> .venv/bin/uvicorn reality_check.api:app --port 8000
```
POST /judge, GET /judge/{id}, GET|POST /rate/{id}, GET /ledger, GET /events, GET / (dashboard).

## Layout
- `reality_check/core/` consensus.py, brier.py, bandit.py vendored from augur; voi.py written fresh.
- `reality_check/evaluators.py` five cheap-tier personas (Groq).
- `reality_check/judge.py` the loop; `panels.py` human-source contract; `store.py` sqlite ledger.
- `reality_check/policy/` spend envelope, bandit routing, protocol wrapper (money-swarm session).
- `stripe_webhook.py`, `terac_client.py`, `linq_client.py`: money-swarm session.
