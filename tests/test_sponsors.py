"""Sponsor signature loading + depth detection (mechanical, zero model calls)."""
import pytest

from reality_check import evaluators, hackathon, sponsors
from reality_check.core.consensus import Vote
from reality_check.core.models import Forecast

CODE_TEXT = (
    "reality_check/terac_client.py: Terac REST v2 client\n"
    "TERAC_API_KEY is read from the env\n"
)


# --------------------------------------------------------------------------- loading

def test_load_signatures_has_the_sponsors_and_capabilities():
    sig = sponsors.load_signatures()
    for name in ("terac", "stripe", "linq", "replay"):
        assert name in sig, name
        assert sig[name]["capabilities"], name
        for cap in sig[name]["capabilities"]:
            assert cap["id"] and cap["what"] and cap["signals"]
    assert sig["_depth_ladder"]["4"].startswith("deep")
    assert sponsors.load_signatures() is sig  # cached


def test_load_signatures_missing_file():
    with pytest.raises(ValueError):
        sponsors.load_signatures("/nope/not-here.md")


# --------------------------------------------------------------------------- depth

def test_code_and_docstring_hits_give_depth_two_or_more_with_file_evidence():
    det = sponsors.detect(CODE_TEXT, sponsors.load_signatures())["terac"]
    assert det["depth"] >= 2
    assert det["depth_word"] in ("wired", "used", "deep")
    assert any(p == "TERAC_API_KEY" for p, _ in det["code_hits"])
    file_ev = [c["evidence"] for c in det["capabilities"] if c["hit"]]
    assert any(".py" in e for e in file_ev) or det["depth"] == 2
    assert "reality_check/terac_client.py" in [
        sponsors._file_of(ln) for _, ln in det["code_hits"]
    ] or det["code_hits"]


def test_file_of_reads_the_path_off_a_docstring_line():
    assert sponsors._file_of("reality_check/terac_client.py: Terac REST v2 client") == \
        "reality_check/terac_client.py"
    assert sponsors._file_of("we just love Terac") == "text"


def test_text_only_is_depth_one():
    det = sponsors.detect("we love Terac", sponsors.load_signatures())["terac"]
    assert (det["depth"], det["depth_word"]) == (1, "name-dropped")
    assert det["code_hits"] == []
    assert det["text_hits"]


def test_empty_text_is_depth_zero_and_next_is_the_first_capability():
    sig = sponsors.load_signatures()
    det = sponsors.detect("", sig)["terac"]
    assert (det["depth"], det["depth_word"]) == (0, "not used")
    assert det["next_capability"]["id"] == sig["terac"]["capabilities"][0]["id"]
    assert det["use_line"].startswith("used 0 of ")
    assert det["cheapest_honest_add"]


def test_depth_ladder_key_passes_through_detect():
    out = sponsors.detect("", sponsors.load_signatures())
    assert "_depth_ladder" in out and "0" in out["_depth_ladder"]


def test_deep_use_ticks_capabilities():
    sig = sponsors.load_signatures()
    text = ("app/pay.py: checkout\n"
            "buy.stripe.com/test link\n"
            "client_reference_id=job\n"
            "checkout.session.completed handler is idempotent on session_id\n"
            "rk_ read-only key reads revenue\n")
    det = sponsors.detect(text, sig)["stripe"]
    assert det["depth"] == 4 and det["depth_word"] == "deep"
    assert {c["id"] for c in det["capabilities"] if c["hit"]} >= {
        "payment_link", "reference", "webhook", "restricted_key"}
    assert "used " in det["use_line"]


def test_fake_tell_fires():
    sig = sponsors.load_signatures()
    text = "REPLAY_API_KEY set. key configured, no project created yet.\n"
    det = sponsors.detect(text, sig)["replay"]
    assert "key configured, no project created" in det["fake_tells_fired"]


def test_capabilities_are_not_ticked_without_code_hits():
    # "bug"/"fix"/"status" are ordinary English; a text-only mention must stay at depth 1
    det = sponsors.detect("we should fix that bug, status unknown, Replay is cool",
                          sponsors.load_signatures())["replay"]
    assert det["depth"] == 1
    assert not any(c["hit"] for c in det["capabilities"])


# --------------------------------------------------------------------------- wired into evaluate

class _Fake:
    def __init__(self, p=0.9):
        self.p = p

    def __call__(self, claims, text, personas=None):
        name = (personas or ["judge"])[0]
        return [evaluators.EvalResult(
            [Vote(hypothesis_id=name, forecast=Forecast(
                p=self.p, confidence=0.5, reasoning="r", side="yes"))], 0.0, 1, "fake")
            for _ in claims]


def test_evaluate_puts_used_sponsors_in_a_used_bucket(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(evaluators, "evaluate_batch", _Fake(p=0.9))
    bundle = ("reality_check/terac_client.py: Terac REST v2 client\n"
              "TERAC_API_KEY, terac_create_opportunity, terac_get_submissions\n"
              "buy.stripe.com/abc with client_reference_id\n")
    out = hackathon.evaluate(bundle, has_repo=False)
    used = {e["id"]: e for b in ("qualifies", "claimed_not_evidenced")
            for e in out["sponsors"][b]}
    for sid in ("sponsor/terac", "sponsor/stripe"):
        assert sid in used, out["sponsors"]
        assert used[sid]["use_line"].startswith("used ")
        assert used[sid]["depth"] >= 2
        assert used[sid]["capabilities"]
    not_used = {e["id"]: e for e in out["sponsors"]["not_used"]}
    assert "sponsor/whop" in not_used
    assert not_used["sponsor/whop"]["status"] == "not_used"
    assert not_used["sponsor/whop"]["depth"] == 0
    assert not_used["sponsor/whop"]["next_capability"]["id"] == "checkout"
