"""Issue #4: the locked judging design (docs/specs/judging-design.md).

Evidence-grounded verdicts (yes|no|not_evidenced + a quote that must literally be in the bundle),
OpenAI primary / Groq fallback, seeded shuffle + batches of 8, per-persona bundles, and the
position-bias stability flag. Nothing here touches the network: every test injects a fake
httpx.Client.
"""
from __future__ import annotations

import json as _json
import re

import pytest

from reality_check import evaluators

OPENAI = "https://api.openai.com/v1"
GROQ = "https://api.groq.com/openai/v1"


def _listed_claims(body: dict) -> list[str]:
    """The numbered claims as the model saw them, in prompt order."""
    content = body["messages"][1]["content"]
    block = content.split("):\n", 1)[1].split("\n\nINPUT", 1)[0]
    return [re.sub(r"^\d+\.\s*", "", line) for line in block.splitlines()]


class _Resp:
    def __init__(self, payload: dict, status: int = 200):
        self._payload = payload
        self.status_code = status
        self.headers: dict = {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._payload


def _ok(items: list[dict]) -> _Resp:
    return _Resp({"choices": [{"message": {"content": _json.dumps({"claims": items})}}],
                  "usage": {"prompt_tokens": 100, "completion_tokens": 50}})


class _Client:
    """Base fake: subclasses implement `answer(claims, body) -> list[dict] | _Resp`."""

    posts: list[dict] = []

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, json=None, headers=None):  # noqa: A002
        type(self).posts.append({"url": url, "body": json})
        claims = _listed_claims(json)
        out = self.answer(claims, json)
        return out if isinstance(out, _Resp) else _ok(out)

    def answer(self, claims, body):  # pragma: no cover - overridden
        raise NotImplementedError


def _install(monkeypatch, cls, *, openai_key: str | None = "sk-test", groq_key: str | None = None):
    cls.posts = []
    monkeypatch.setattr(evaluators.httpx, "Client", cls)
    for env, val in (("OPENAI_API_KEY", openai_key), ("GROQ_API_KEY", groq_key)):
        if val:
            monkeypatch.setenv(env, val)
        else:
            monkeypatch.delenv(env, raising=False)


TEXT = "Acme charges 20 dollars a roast. Three teams paid so far."


# --- (a) verdicts, quote verification, p mapping -------------------------------------

class _VerdictClient(_Client):
    def answer(self, claims, body):
        items = []
        for i, c in enumerate(claims):
            if "priced" in c:
                items.append({"idx": i, "verdict": "yes", "quote": "charges 20 dollars", "reasoning": "price is on the page"})
            elif "fabricated" in c:
                items.append({"idx": i, "verdict": "yes", "quote": "we have 4000 paying customers", "reasoning": "traction"})
            elif "refuted" in c:
                items.append({"idx": i, "verdict": "no", "quote": "Three teams paid so far", "reasoning": "only three"})
            else:
                items.append({"idx": i, "verdict": "not_evidenced", "quote": "", "reasoning": "silent"})
        return items


def test_verdicts_map_to_p_and_an_unverifiable_quote_is_downgraded(monkeypatch):
    _install(monkeypatch, _VerdictClient)
    claims = ["the product is priced", "the fabricated traction claim", "the refuted scale claim", "quiet claim"]
    out = evaluators.evaluate_batch(claims, TEXT, ["judge"])

    fcs = [r.votes[0].forecast for r in out]
    assert [f.verdict for f in fcs] == ["yes", "not_evidenced", "no", "not_evidenced"]
    assert [f.p for f in fcs] == [1.0, 0.5, 0.0, 0.5]
    assert [f.side for f in fcs] == ["yes", "skip", "no", "skip"]
    # the quote survives on a verified verdict, and vanishes on a downgraded one
    assert fcs[0].quote == "charges 20 dollars"
    assert fcs[1].quote is None
    assert fcs[1].reasoning.startswith("quote not found: we have 4000 paying customers")
    # no verbalized probability anywhere in the prompt
    sys_prompt = _VerdictClient.posts[0]["body"]["messages"][0]["content"]
    assert "probability" not in sys_prompt and "not_evidenced" in sys_prompt


def test_quote_match_is_case_and_whitespace_insensitive(monkeypatch):
    class _C(_Client):
        def answer(self, claims, body):
            return [{"idx": 0, "verdict": "yes", "quote": "CHARGES   20\n dollars", "reasoning": "ok"}]

    _install(monkeypatch, _C)
    fc = evaluators.evaluate_batch(["priced"], TEXT, ["judge"])[0].votes[0].forecast
    assert fc.verdict == "yes" and fc.p == 1.0


def test_stub_mode_fills_the_new_fields(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    out = evaluators.evaluate_batch(["a", "b", "c", "d"], TEXT, ["judge", "customer"])
    assert all(r.provider == "stub" for r in out)
    verdicts = {v.forecast.verdict for r in out for v in r.votes}
    assert verdicts <= {"yes", "no", "not_evidenced"} and len(verdicts) > 1
    for r in out:
        for v in r.votes:
            assert v.forecast.p == {"yes": 1.0, "no": 0.0, "not_evidenced": 0.5}[v.forecast.verdict]
    # deterministic
    again = evaluators.evaluate_batch(["a", "b", "c", "d"], TEXT, ["judge", "customer"])
    assert [v.forecast.verdict for r in again for v in r.votes] == [v.forecast.verdict for r in out for v in r.votes]


# --- (b) provider order: OpenAI primary, Groq fallback --------------------------------

def test_primary_is_openai(monkeypatch):
    _install(monkeypatch, _VerdictClient, openai_key="sk-test", groq_key=None)
    out = evaluators.evaluate_batch(["the product is priced"], TEXT, ["judge"])
    assert [p["url"] for p in _VerdictClient.posts] == [f"{OPENAI}/chat/completions"]
    assert _VerdictClient.posts[0]["body"]["model"] == evaluators.MODEL == "gpt-4o-mini"
    assert out[0].provider == f"openai:{evaluators.MODEL}"


def test_openai_failure_falls_back_to_groq(monkeypatch):
    class _C(_Client):
        def answer(self, claims, body):
            if type(self).posts[-1]["url"].startswith(OPENAI):
                return _Resp({}, status=500)
            return [{"idx": i, "verdict": "yes", "quote": "Three teams paid so far", "reasoning": "ok"}
                    for i in range(len(claims))]

    _install(monkeypatch, _C, openai_key="sk-test", groq_key="gsk-test")
    out = evaluators.evaluate_batch(["the product is priced"], TEXT, ["judge"])
    urls = [p["url"] for p in _C.posts]
    assert urls == [f"{OPENAI}/chat/completions", f"{GROQ}/chat/completions"]
    assert _C.posts[1]["body"]["model"] == evaluators.FALLBACK_MODEL == "llama-3.1-8b-instant"
    assert out[0].votes[0].forecast.verdict == "yes"
    assert out[0].provider == f"groq:{evaluators.FALLBACK_MODEL}"


def test_groq_only_key_still_works(monkeypatch):
    """Today's deployments carry a Groq key and no OpenAI key; that must not become stub mode."""
    _install(monkeypatch, _VerdictClient, openai_key=None, groq_key="gsk-test")
    out = evaluators.evaluate_batch(["the product is priced"], TEXT, ["judge"])
    assert [p["url"] for p in _VerdictClient.posts] == [f"{GROQ}/chat/completions"]
    assert out[0].provider == f"groq:{evaluators.FALLBACK_MODEL}"


def test_second_seat_uses_a_second_family_when_configured(monkeypatch):
    _install(monkeypatch, _VerdictClient, openai_key="sk-test", groq_key=None)
    monkeypatch.setenv("MISTRAL_KEY", "m-test")
    monkeypatch.setattr(evaluators, "SECOND_KEY_ENV", "MISTRAL_KEY")
    monkeypatch.setattr(evaluators, "SECOND_BASE", "https://api.mistral.ai/v1")
    monkeypatch.setattr(evaluators, "SECOND_MODEL", "mistral-small")
    evaluators.evaluate_batch(["the product is priced"], TEXT, ["judge", "customer", "engineer"])
    urls = [p["url"] for p in _VerdictClient.posts]
    assert urls[0].startswith(OPENAI)
    assert urls[1] == "https://api.mistral.ai/v1/chat/completions"
    assert urls[2].startswith(OPENAI)
    # seat 3 is the same family at temperature, so the persona is what varies
    assert _VerdictClient.posts[2]["body"]["temperature"] == 0.7
    assert _VerdictClient.posts[0]["body"]["temperature"] == 0.4


# --- (c) shuffle + batches of 8 -------------------------------------------------------

class _EchoClient(_Client):
    """Answers yes for claims whose text says so, keyed by the claim text (not its position)."""

    omit_first = False

    def answer(self, claims, body):
        items = []
        for i, c in enumerate(claims):
            if type(self).omit_first and i == 0 and len(claims) > 1:
                continue
            v = "yes" if c.endswith("-yes") else "no"
            items.append({"idx": i, "verdict": v, "quote": "Three teams paid so far", "reasoning": c})
        return items


def test_claims_are_shuffled_and_mapped_back(monkeypatch):
    _EchoClient.omit_first = False
    _install(monkeypatch, _EchoClient)
    claims = [f"claim-{i}-{'yes' if i % 2 == 0 else 'no'}" for i in range(8)]
    out = evaluators.evaluate_batch(claims, TEXT, ["judge"])

    listed = _listed_claims(_EchoClient.posts[0]["body"])
    assert sorted(listed) == sorted(claims)
    assert listed != claims, "claims must be shuffled, not sent in rubric order"
    # each result carries the verdict for ITS OWN claim text
    for claim, res in zip(claims, out, strict=True):
        assert res.votes[0].forecast.reasoning == claim
        assert res.votes[0].forecast.verdict == ("yes" if claim.endswith("-yes") else "no")


def test_shuffle_is_deterministic_per_persona(monkeypatch):
    _EchoClient.omit_first = False
    _install(monkeypatch, _EchoClient)
    claims = [f"claim-{i}-no" for i in range(8)]
    evaluators.evaluate_batch(claims, TEXT, ["judge"])
    first = _listed_claims(_EchoClient.posts[0]["body"])
    _EchoClient.posts = []
    evaluators.evaluate_batch(claims, TEXT, ["judge"])
    assert _listed_claims(_EchoClient.posts[0]["body"]) == first


def test_twenty_claims_are_three_calls_per_persona(monkeypatch):
    _EchoClient.omit_first = False
    _install(monkeypatch, _EchoClient)
    claims = [f"claim-{i}-no" for i in range(20)]
    out = evaluators.evaluate_batch(claims, TEXT, ["judge", "customer"])
    assert evaluators.MAX_CLAIMS_PER_CALL == 8
    assert len(_EchoClient.posts) == 3 * 2  # ceil(20/8) = 3 chunks per persona, no repair needed
    sizes = sorted(len(_listed_claims(p["body"])) for p in _EchoClient.posts[:3])
    assert sizes == [4, 8, 8]
    assert len(out) == 20 and all(len(r.votes) == 2 for r in out)
    # the prompt states the count and the index range
    sys0 = _EchoClient.posts[0]["body"]["messages"][0]["content"]
    assert "There are 8 claims, numbered 0 to 7" in sys0


def test_a_missing_answer_triggers_one_repair_call_per_chunk(monkeypatch):
    _EchoClient.omit_first = True
    _install(monkeypatch, _EchoClient)
    claims = [f"claim-{i}-no" for i in range(20)]
    out = evaluators.evaluate_batch(claims, TEXT, ["judge"])
    _EchoClient.omit_first = False
    assert len(_EchoClient.posts) == 6  # 3 chunks + 1 repair each
    repairs = [p for p in _EchoClient.posts if "CLAIMS (1):" in p["body"]["messages"][1]["content"]]
    assert len(repairs) == 3
    # the repair pass recovers the dropped claim, so no claim is left without an answer
    assert len(out) == 20
    assert all(r.votes[0].forecast.verdict == "no" for r in out)


# --- (d) per-persona bundles ----------------------------------------------------------

def test_text_by_persona_sends_each_seat_its_own_bundle(monkeypatch):
    _install(monkeypatch, _VerdictClient)
    repo = "reality_check/policy.py: the spend envelope. reality_check/ledger.py: every dollar."
    pitch = "Acme charges 20 dollars a roast."
    evaluators.evaluate_batch(["the product is priced"], "fallback bundle",
                              ["judge", "engineer"],
                              text_by_persona={"judge": pitch, "engineer": repo})
    bodies = [p["body"]["messages"][1]["content"] for p in _VerdictClient.posts]
    assert pitch in bodies[0] and repo not in bodies[0]
    assert repo in bodies[1] and pitch not in bodies[1]


def test_missing_persona_bundle_falls_back_to_text(monkeypatch):
    _install(monkeypatch, _VerdictClient)
    evaluators.evaluate_batch(["the product is priced"], TEXT, ["judge", "customer"],
                              text_by_persona={"judge": "judge-only bundle"})
    bodies = [p["body"]["messages"][1]["content"] for p in _VerdictClient.posts]
    assert "judge-only bundle" in bodies[0]
    assert TEXT in bodies[1]


def test_engineer_persona_exists_and_panel_seats_are_locked():
    assert evaluators.PANEL_SEATS == ("judge", "customer", "engineer")
    assert evaluators.panel_for("autonomy") == ["judge", "customer", "engineer"]
    assert "engineer" in evaluators.PERSONAS
    assert "guardrail" in evaluators.PERSONAS["engineer"]


# --- (e) position-bias stability ------------------------------------------------------

class _OrderSensitiveClient(_Client):
    """Answers `flipper` yes when it is first in the prompt and no otherwise: a position-bias
    victim by construction."""

    def answer(self, claims, body):
        items = []
        for i, c in enumerate(claims):
            if "flipper" in c:
                v = "yes" if i == 0 else "no"
            else:
                v = "yes"
            items.append({"idx": i, "verdict": v, "quote": "Three teams paid so far", "reasoning": c})
        return items


def test_stability_check_flags_the_flipped_claim(monkeypatch):
    _install(monkeypatch, _OrderSensitiveClient)
    claims = ["steady claim a", "the flipper claim", "steady claim b"]
    out = evaluators.evaluate_batch(claims, TEXT, ["judge"], stability_check=True)
    assert len(_OrderSensitiveClient.posts) == 2  # forward pass + reversed pass
    fwd = _listed_claims(_OrderSensitiveClient.posts[0]["body"])
    assert _listed_claims(_OrderSensitiveClient.posts[1]["body"]) == list(reversed(fwd))
    flags = {c: r.votes[0].forecast.unstable for c, r in zip(claims, out, strict=True)}
    assert flags["the flipper claim"] is True
    assert flags["steady claim a"] is False and flags["steady claim b"] is False


def test_stability_check_is_off_by_default(monkeypatch):
    _install(monkeypatch, _OrderSensitiveClient)
    out = evaluators.evaluate_batch(["steady claim a", "the flipper claim"], TEXT, ["judge"])
    assert len(_OrderSensitiveClient.posts) == 1
    assert all(v.forecast.unstable is False for r in out for v in r.votes)
