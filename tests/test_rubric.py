"""Issue #2: the lens rubric + batched evaluation.

Batching is the whole point: one model call per persona per lens, never per claim (Groq free
tier is ~30 RPM). Objective claims cost zero model calls and stay "no evidence yet" until a
probe speaks. Nothing here touches the network: no GROQ_API_KEY -> stub path, and the one
HTTP test injects a fake httpx.Client.
"""
from __future__ import annotations

import json as _json
import re

from fastapi.testclient import TestClient

from reality_check import evaluators, judge, lenses
from reality_check.api import app

c = TestClient(app)

CLAIM_ID_RE = re.compile(r"^[a-z_]+/[a-z0-9-]+$")

FULL_INPUT = "Acme: AI roast of pitch decks for YC founders, $20 a roast, 3 paid so far."


# --- (a) stub path -----------------------------------------------------------------

def test_evaluate_batch_stub_returns_one_result_per_claim():
    claims = ["A is true", "B is true", "C is true"]
    out = evaluators.evaluate_batch(claims, "some input", ["skeptic", "operator"])
    assert len(out) == len(claims)
    for r in out:
        assert len(r.votes) == 2 and r.provider == "stub" and r.cost_usd == 0.0
        assert [v.hypothesis_id for v in r.votes] == ["skeptic", "operator"]
    # deterministic and claim-specific: different claims do not get identical forecasts
    assert len({r.votes[0].forecast.p for r in out}) > 1
    assert evaluators.evaluate_batch([], "x", ["skeptic"]) == []


# --- (b) one POST per persona; a malformed idx skips only its own claim -------------

class _FakeResponse:
    status_code = 200
    headers: dict = {}

    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    """Answers every batch: claim 1 is malformed (p out of any usable form), the rest parse."""

    posts: list[dict] = []

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, json=None, headers=None):  # noqa: A002
        _FakeClient.posts.append({"url": url, "body": json})
        body_text = json["messages"][1]["content"]
        n = len(body_text.split("):\n", 1)[1].split("\n\nINPUT")[0].splitlines())
        items = []
        for i in range(n):
            if i == 1:
                items.append({"idx": "not-a-number", "p": 0.9})
                continue
            items.append({"idx": i, "verdict": "yes", "quote": "input", "reasoning": f"ok {i}"})
        content = _json.dumps({"claims": items})
        return _FakeResponse({"choices": [{"message": {"content": content}}],
                              "usage": {"prompt_tokens": 100, "completion_tokens": 50}})


def test_batch_makes_one_post_per_persona_and_malformed_idx_only_skips_itself(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _FakeClient.posts = []
    monkeypatch.setattr(evaluators.httpx, "Client", _FakeClient)

    claims = ["claim zero", "claim one", "claim two", "claim three"]
    personas = ["skeptic", "operator"]
    out = evaluators.evaluate_batch(claims, "input text", personas)

    # one call per persona for the whole list, plus one repair call per persona for the unanswered
    # claim (the fake returns a non-numeric idx for claim 1, i.e. no usable answer)
    assert len(_FakeClient.posts) == 2 * len(personas)
    repair_posts = [p for p in _FakeClient.posts if "CLAIMS (1):" in p["body"]["messages"][1]["content"]]
    assert len(repair_posts) == len(personas)
    assert len(out) == len(claims)
    for i, r in enumerate(out):
        sides = [v.forecast.side for v in r.votes]
        # verdict yes -> p 1.0 (derived, not verbalized); the quote is verified against the bundle
        assert sides == ["yes", "yes"] and r.votes[0].forecast.p == 1.0
        assert r.votes[0].forecast.verdict == "yes" and r.votes[0].forecast.quote == "input"
    assert sum(r.cost_usd for r in out) > 0


def test_batch_chunks_above_the_cap(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _FakeClient.posts = []
    monkeypatch.setattr(evaluators.httpx, "Client", _FakeClient)
    n = evaluators.MAX_CLAIMS_PER_CALL + 3
    out = evaluators.evaluate_batch([f"claim {i}" for i in range(n)], "input", ["skeptic"])
    assert len(out) == n and len(_FakeClient.posts) == 2 + 2  # 2 chunks + 1 repair each


# --- (c) run order + claim ids ------------------------------------------------------

def test_run_order_excludes_disabled_lenses():
    names = [l.name for l in lenses.run_order()]
    for off in ("competition", "economics", "trust", "projections"):
        assert off not in names
        assert lenses.LENS_BY_NAME[off].enabled is False   # still defined, just not run today
    for on in ("clarity", "demand", "viability", "stability", "security", "seo", "legal",
               "accessibility", "agent_ready", "ux"):
        assert on in names


def test_claim_ids_are_unique_and_well_formed():
    rows = lenses.claims_for_run(extra_claims=["The team's own claim"])
    ids = [cid for _c, _l, cid in rows]
    assert len(ids) == len(set(ids))
    assert all(CLAIM_ID_RE.match(i) for i in ids), [i for i in ids if not CLAIM_ID_RE.match(i)]
    assert "demand/payer" in ids and "clarity/what-it-does" in ids
    # ids key on the pinned slug, so editing a claim's wording never moves the report's key
    assert lenses.claim_id("demand", lenses.LENS_BY_NAME["demand"].claims[0]) == "demand/payer"
    objective = {cid for cl, _l, cid in rows if cl.mode == "objective"}
    assert objective and objective <= set(ids)


def test_claims_for_run_mode_filter():
    model = lenses.claims_for_run("model")
    obj = lenses.claims_for_run("objective")
    assert all(cl.mode in ("model", "both") for cl, _l, _i in model)
    assert all(cl.mode == "objective" for cl, _l, _i in obj)
    assert len(model) + len(obj) == len(lenses.claims_for_run())


# --- (d) a full job: lens/claim_id on the verdict, objective claims not model-judged --

def test_full_check_without_url_leaves_objective_claims_without_evidence():
    r = c.post("/judge", json={"input": FULL_INPUT, "sku": "full_reality_check"},
               headers={"X-RC-Paid": "25"})
    assert r.status_code == 200, r.text
    v = r.json()
    rubric = {cid: cl for cl, _l, cid in lenses.claims_for_run()}
    assert v["claims"] and len(v["claims"]) == len(rubric)
    for cv in v["claims"]:
        assert cv["lens"] and CLAIM_ID_RE.match(cv["claim_id"])
        mode = rubric[cv["claim_id"]].mode
        if mode == "objective":
            assert cv["evidence_state"] == "none", cv["claim_id"]
            assert cv["verdict"] == "undecided", "objective claims never carry a model verdict"
            assert cv["p_internal"] == 0.5
        else:
            assert cv["evidence_state"] == "model"
    assert not any(cv["lens"] in ("economics", "competition", "trust", "projections") for cv in v["claims"])


def test_full_check_with_url_lets_probes_back_an_objective_claim(monkeypatch):
    from reality_check import judge as judge_module
    from reality_check import probes as probes_module

    def fake_probes_run(url, **kwargs):
        return {"url": url, "ok": True, "fetched": True, "pages": [url],
                "findings": [{"id": "live/https-missing", "severity": "error", "page": url,
                              "message": "not https", "fix": None, "evidence": url}],
                "ttfb_ms": 10.0, "status": 200, "agentready": None, "skipped": [], "error": None,
                "namespaces": ["audit", "live"], "unknown": []}

    class _SyncThread:
        def __init__(self, target=None, daemon=None):
            self._target = target

        def start(self):
            if self._target:
                self._target()

    monkeypatch.setattr(probes_module, "run", fake_probes_run)
    monkeypatch.setattr(judge_module, "probes", probes_module)
    monkeypatch.setattr(judge_module.threading, "Thread", _SyncThread)

    r = c.post("/judge", json={"input": FULL_INPUT, "sku": "full_reality_check",
                               "url": "https://insecure.example.com/"}, headers={"X-RC-Paid": "25"})
    assert r.status_code == 200, r.text
    v = c.get(f"/judge/{r.json()['job_id']}").json()
    by_id = {cv["claim_id"]: cv for cv in v["claims"]}
    https = by_id["security/https"]
    assert https["evidence_state"] == "probe" and https["verdict"] == "no"
    assert https["objective"]["failing"] == ["live/https-missing"]
    # a claim whose namespace this run never produced stays "no evidence yet"
    assert by_id["ux/no-open-bugs"]["evidence_state"] == "none"


# --- (e) the call budget ------------------------------------------------------------

def test_full_run_model_call_count_is_bounded(monkeypatch):
    calls: list[tuple[int, int]] = []
    real = evaluators.evaluate_batch

    def counting(claims, text, personas=None):
        calls.append((len(claims), len(personas or [])))
        return real(claims, text, personas)

    monkeypatch.setattr(evaluators, "evaluate_batch", counting)
    import time
    t0 = time.time()
    r = c.post("/judge", json={"input": FULL_INPUT, "sku": "full_reality_check"},
               headers={"X-RC-Paid": "25"})
    elapsed = time.time() - t0
    assert r.status_code == 200, r.text

    expected = sum(min(len(l.personas), judge.RUBRIC_PERSONAS_MAX) for l in lenses.run_order()
                   if any(cl.mode in ("model", "both") for cl in l.claims))
    # the hackathon rubric (judge.py _launch_hackathon) adds one call per section per persona
    # (4 sections x 2 personas without a repo); it runs in a thread so give it a moment
    import time as _t
    for _ in range(50):
        if sum(personas for _n, personas in calls) >= expected + 8:
            break
        _t.sleep(0.05)
    n_model_calls = sum(personas for _n, personas in calls)
    assert n_model_calls == expected + 8
    # effective HTTP calls after evaluate_batch's internal chunking (MAX_CLAIMS_PER_CALL per call):
    # the sponsor section alone is ~40 claims, so it chunks. Groq free tier is ~30 RPM; the rubric
    # + hackathon run must stay near that or the judge takes >1 min on a cold key.
    import math
    effective = sum(personas * math.ceil(n / evaluators.MAX_CLAIMS_PER_CALL) for n, personas in calls)
    # 40 at MAX_CLAIMS_PER_CALL=8 (was 36 at 12): small numbered batches beat position bias, and
    # OpenAI (now primary) has no 30 RPM ceiling.
    assert effective <= 40, f"effective model calls per full run: {effective}"
    assert elapsed < 2.0, f"stub-mode full check took {elapsed:.2f}s"
