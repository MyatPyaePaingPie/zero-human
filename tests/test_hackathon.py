"""Hackathon rubric evaluation: parsing, hint grep, batching, thresholds, buckets, stamp, top3.

Stub mode only: GROQ_API_KEY is unset by conftest and every model path is a fake, so no network.
"""
import re

import pytest

from reality_check import evaluators, hackathon
from reality_check.core.consensus import Vote
from reality_check.core.models import Forecast

TEXT = "We built a thing. Payments via stripe. Deployed on render."


@pytest.fixture(autouse=True)
def _no_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)


class FakeBatch:
    """Counts calls; p per claim comes from `p_for(claim_text)` or a constant."""

    def __init__(self, p=0.9, p_for=None, raises=False):
        self.calls = 0
        self.personas = []
        self.p = p
        self.p_for = p_for
        self.raises = raises

    def __call__(self, claims, text, personas=None):
        self.calls += 1
        self.personas.append(list(personas or []))
        if self.raises:
            raise RuntimeError("groq down")
        name = (personas or ["judge"])[0]
        out = []
        for c in claims:
            p = self.p_for(c) if self.p_for else self.p
            fc = Forecast(p=p, confidence=0.5, reasoning=f"r[{name}]", side="yes" if p > 0.5 else "no")
            out.append(evaluators.EvalResult([Vote(hypothesis_id=name, forecast=fc)], 0.0, 1, "fake"))
        return out


def install(monkeypatch, fake):
    monkeypatch.setattr(evaluators, "evaluate_batch", fake)
    return fake


# --------------------------------------------------------------------------- rubric parsing

def test_load_rubric_sections_and_ids():
    r = hackathon.load_rubric()
    assert (len(r["judging"]), len(r["sponsors"]), len(r["messaging"]), len(r["technical"])) == (6, 10, 5, 3)
    assert r["hackathon"].startswith("Zero Human Company Hackathon")
    for sec in ("judging", "sponsors", "messaging", "technical"):
        for item in r[sec]:
            assert re.match(r"^(judge|sponsor|msg|tech)/[a-z0-9-]+$", item["id"]), item["id"]
            assert item["claims"]


def test_load_rubric_is_cached():
    assert hackathon.load_rubric() is hackathon.load_rubric()


def test_load_rubric_missing_block(tmp_path):
    bad = tmp_path / "no-block.md"
    bad.write_text("# prose only, no fenced json\n")
    with pytest.raises(ValueError, match="json"):
        hackathon.load_rubric(str(bad))


def test_load_rubric_invalid_json(tmp_path):
    bad = tmp_path / "broken.md"
    bad.write_text("```json\n{not json,}\n```\n")
    with pytest.raises(ValueError, match="does not parse"):
        hackathon.load_rubric(str(bad))


# --------------------------------------------------------------------------- sponsor hint grep

def test_sponsor_evidence_finds_terac_case_insensitively():
    r = hackathon.load_rubric()
    hints = hackathon.sponsor_evidence("we call mcp__terac__terac_create_opportunity in the loop", r)
    assert "terac" in [h.lower() for h in hints["sponsor/terac"]]
    assert hints["sponsor/linq"] == []


def test_sponsor_evidence_none_on_unrelated_text():
    r = hackathon.load_rubric()
    hints = hackathon.sponsor_evidence("a poem about bicycles and weather", r)
    assert all(v == [] for v in hints.values())


# --------------------------------------------------------------------------- call budget

def test_evaluate_no_repo_is_three_sections_times_personas(monkeypatch):
    fake = install(monkeypatch, FakeBatch(p=0.9))
    out = hackathon.evaluate(TEXT, has_repo=False)
    assert fake.calls == 4 * 2 == out["model_calls"]  # judging, sponsors, messaging, autonomy
    assert out["technical"] == []
    assert out["personas"] == ["judge", "customer"]
    assert all(len(p) == 1 for p in fake.personas)


def test_evaluate_with_repo_is_four_sections(monkeypatch):
    fake = install(monkeypatch, FakeBatch(p=0.9))
    out = hackathon.evaluate(TEXT, has_repo=True)
    assert fake.calls == 5 * 2 == out["model_calls"]  # + technical with a repo
    assert len(out["technical"]) == 3


def test_evaluate_output_keys_and_ordering(monkeypatch):
    install(monkeypatch, FakeBatch(p=0.9))
    out = hackathon.evaluate(TEXT, has_repo=True)
    assert set(out) == {"rubric_version", "submission_checklist", "personas", "model_calls", "judging", "sponsors", "autonomy", "autonomy_stamp", "autonomy_note",
                        "messaging", "technical", "stamp", "top3", "warnings"}
    weights = [i["weight"] for i in out["judging"]]
    assert weights == sorted(weights, reverse=True)
    assert set(out["sponsors"]) == {"qualifies", "claimed_not_evidenced", "cheapest_to_add", "not_used"}
    row = out["judging"][0]["claims"][0]
    assert set(row) == {"text", "p", "side", "evidence_state", "reasoning"}
    assert row["evidence_state"] == "model"
    assert out["submission_checklist"] == hackathon.load_rubric()["submission_checklist"]
    # terac is the host and the required rule: it leads whatever bucket it lands in
    for bucket in out["sponsors"].values():
        ids = [e["id"] for e in bucket]
        if "sponsor/terac" in ids:
            assert ids[0] == "sponsor/terac"


# --------------------------------------------------------------------------- thresholds

@pytest.mark.parametrize("p,status", [(0.9, "pass"), (0.5, "partial"), (0.1, "fail")])
def test_status_thresholds(monkeypatch, p, status):
    install(monkeypatch, FakeBatch(p=p))
    out = hackathon.evaluate(TEXT, has_repo=True)
    assert {i["status"] for i in out["judging"]} == {status}
    assert {i["status"] for i in out["messaging"]} == {status}
    assert {i["status"] for i in out["technical"]} == {status}


def test_why_and_fix_quote_the_weakest_claim(monkeypatch):
    r = hackathon.load_rubric()
    weakest = r["judging"][0]["claims"][-1]
    install(monkeypatch, FakeBatch(p_for=lambda c: 0.1 if c == weakest else 0.9))
    out = hackathon.evaluate(TEXT, has_repo=False)
    item = [i for i in out["judging"] if i["id"] == r["judging"][0]["id"]][0]
    assert item["why"] == f"weakest: {weakest}"
    assert item["fix"] == f"Say or show it: {weakest}"


# --------------------------------------------------------------------------- sponsor buckets

def _sponsor_rubric():
    return {
        "hackathon": "test",
        "judging": [{"id": "judge/x", "title": "X", "weight": 3, "claims": ["jc"]}],
        "messaging": [{"id": "msg/x", "theme": "T", "claims": ["mc"]}],
        "technical": [{"id": "tech/x", "title": "T", "claims": ["tc"]}],
        "sponsors": [
            {"id": "sponsor/req", "name": "Req", "required": True,
             "claims": ["req claim"], "evidence_hints": ["reqhint"]},
            {"id": "sponsor/good", "name": "Good", "required": False,
             "claims": ["good claim"], "evidence_hints": ["goodhint"]},
            {"id": "sponsor/claimed", "name": "Claimed", "required": False,
             "claims": ["claimed claim"], "evidence_hints": ["nowherehint"]},
            {"id": "sponsor/cheap", "name": "Cheap", "required": False,
             "claims": ["cheap claim"], "evidence_hints": ["cheaphint"]},
            {"id": "sponsor/costly", "name": "Costly", "required": False,
             "claims": ["c " * 100], "evidence_hints": ["costlyhint"]},
        ],
    }


def test_sponsor_buckets(monkeypatch):
    rub = _sponsor_rubric()
    ps = {"good claim": 0.9, "claimed claim": 0.8, "cheap claim": 0.1, "c " * 100: 0.1,
          "req claim": 0.1}
    install(monkeypatch, FakeBatch(p_for=lambda c: ps.get(c, 0.9)))
    out = hackathon.evaluate("mentions goodhint only", has_repo=False, rubric=rub)
    s = out["sponsors"]
    assert [e["id"] for e in s["qualifies"]] == ["sponsor/good"]
    assert [e["id"] for e in s["claimed_not_evidenced"]] == ["sponsor/claimed"]
    assert [e["id"] for e in s["cheapest_to_add"]] == ["sponsor/req", "sponsor/cheap"]
    assert [e["id"] for e in s["not_used"]] == ["sponsor/costly"]
    assert s["cheapest_to_add"][0]["required"] is True
    assert len(s["cheapest_to_add"]) <= 3


def test_cheapest_to_add_capped_at_three(monkeypatch):
    rub = _sponsor_rubric()
    for i in range(4):
        rub["sponsors"].append({"id": f"sponsor/x{i}", "name": f"X{i}", "required": False,
                                "claims": ["short claim"], "evidence_hints": [f"x{i}hint"]})
    install(monkeypatch, FakeBatch(p=0.1))
    out = hackathon.evaluate("nothing here", has_repo=False, rubric=rub)
    assert len(out["sponsors"]["cheapest_to_add"]) == 3
    assert out["sponsors"]["cheapest_to_add"][0]["required"] is True


# --------------------------------------------------------------------------- stamp + top3

def test_stamp_contender(monkeypatch):
    rub = _sponsor_rubric()
    install(monkeypatch, FakeBatch(p=0.9))
    out = hackathon.evaluate("reqhint goodhint nowherehint cheaphint costlyhint", has_repo=False, rubric=rub)
    assert out["stamp"] == "contender"


def test_stamp_fixable_when_heavy_items_are_only_partial(monkeypatch):
    rub = _sponsor_rubric()
    install(monkeypatch, FakeBatch(p_for=lambda c: 0.5 if c == "jc" else 0.8))
    out = hackathon.evaluate("no hints at all", has_repo=False, rubric=rub)
    assert [e["id"] for e in out["sponsors"]["claimed_not_evidenced"]] != []
    assert out["stamp"] == "fixable_by_1830"


def test_stamp_not_yet(monkeypatch):
    rub = _sponsor_rubric()
    install(monkeypatch, FakeBatch(p=0.1))
    out = hackathon.evaluate("no hints at all", has_repo=False, rubric=rub)
    assert out["stamp"] == "not_yet"


def test_top3_length_and_ordering(monkeypatch):
    install(monkeypatch, FakeBatch(p=0.1))
    r = hackathon.load_rubric()
    out = hackathon.evaluate("nothing evidenced", has_repo=False)
    assert len(out["top3"]) == 3
    heaviest = max(r["judging"], key=lambda i: i["weight"])
    assert out["top3"][0].startswith(heaviest["title"])
    assert out["top3"] == out["top3"][:3]


def test_top3_empty_when_everything_passes(monkeypatch):
    rub = _sponsor_rubric()
    install(monkeypatch, FakeBatch(p=0.9))
    out = hackathon.evaluate("reqhint goodhint nowherehint cheaphint costlyhint", has_repo=False, rubric=rub)
    assert out["top3"] == []


# --------------------------------------------------------------------------- fail closed

def test_evaluator_failure_marks_unknown_without_raising(monkeypatch):
    install(monkeypatch, FakeBatch(raises=True))
    out = hackathon.evaluate(TEXT, has_repo=True)
    assert {i["status"] for i in out["judging"]} == {"unknown"}
    assert {i["status"] for i in out["messaging"]} == {"unknown"}
    assert {i["status"] for i in out["technical"]} == {"unknown"}
    assert all(e["status"] == "unknown" for b in out["sponsors"].values() for e in b)
    assert not out["sponsors"]["qualifies"]
    assert len(out["warnings"]) == 5
    assert out["stamp"] == "not_yet"


def test_messaging_rewrite_and_where(monkeypatch):
    install(monkeypatch, FakeBatch(p=0.1))
    out = hackathon.evaluate(TEXT, has_repo=False)
    first = [m for m in out["messaging"] if m["id"] == "msg/first-screen"][0]
    assert first["where"] == "landing page hero, above the fold"
    assert first["rewrite"].startswith("Put one line on the first screen")
    assert len(first["rewrite"]) > len("Put one line on the first screen that makes this true: ")


def test_personas_registered():
    assert "judge" in evaluators.PERSONAS and "customer" in evaluators.PERSONAS


def test_judge_launches_hackathon_eval_for_full_check(monkeypatch):
    """judge.start runs the rubric in a thread and patches state.hackathon."""
    import threading
    from fastapi.testclient import TestClient
    from reality_check import judge as judge_module, store
    from reality_check.api import app
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    done = threading.Event()
    real = judge_module._launch_hackathon
    def sync_launch(job_id, text, has_repo):
        from reality_check import hackathon
        store.patch_job_state(job_id, "hackathon", hackathon.evaluate(text, has_repo=has_repo))
        done.set()
    monkeypatch.setattr(judge_module, "_launch_hackathon", sync_launch)
    c = TestClient(app)
    r = c.post("/judge", json={"input": "Acme sells rockets to hobbyists via Stripe; agents run support.", "sku": "full_reality_check",
                               "evidence_standard": "voi_routed", "max_budget_usd": 0})
    assert r.status_code == 200, r.text
    assert done.is_set()
    st = store.get_job(r.json()["job_id"])["state"]["hackathon"]
    assert st["stamp"] in ("contender", "fixable_by_1830", "not_yet") and len(st["judging"]) == 6


def test_autonomy_section_runs_and_stamps(monkeypatch):
    from reality_check import evaluators, hackathon
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    out = hackathon.evaluate("Acme: signed spend envelope, agents stop when price unknown.", has_repo=False)
    assert len(out["autonomy"]) == 7 and all(a["id"].startswith("auto/") for a in out["autonomy"])
    assert out["autonomy_stamp"] in ("autonomous", "human_in_the_loop", "not_autonomous")
    assert out["model_calls"] == 8  # judging, sponsors, messaging, autonomy x 2 personas
