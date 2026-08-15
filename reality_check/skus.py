"""SKU presets: which claims and which evaluator personas a product uses.

The router (judge.py) is SKU-agnostic; a SKU is claims + personas + a human question style.
demand_check rubric is the money-swarm demand-to-build gate verbatim; verified_autonomous claims come from the team being audited.
"""
from __future__ import annotations

SKUS: dict[str, dict] = {
    "reality_check": {
        "price_usd": 8.0,
        "claims": ["A first-time visitor can tell what this company does within ten seconds"],
        "personas": ["skeptic", "operator", "outsider", "buyer", "designer"],
        "human_question": "After reading this, can you tell what this company does? Say yes or no, then say in one line what you think it does.",
    },
    "demand_check": {
        "price_usd": 10.0,
        "claims": [
            "payer: a specific person or role who would pay for this is named",
            "painful job: the problem is painful enough that people already spend money or hours on it today",
            "current workaround or spend: what people do about it today is stated (tool, hire, manual work, or ignore at a cost)",
            "reachable audience: the team can reach those people themselves, without a marketplace doing it for them",
            "smallest paid test: a paid test could launch in seven days or less",
            "kill rule: there is a stated condition under which the team would kill this",
        ],
        # Gate (money-swarm demand-to-build): all six evidenced or "not real yet". A paid-test
        # DESCRIPTION is not a result; only paid_test_cleared=true counts, so claim 5 passing
        # still leaves the company at "not real yet" until a paid test actually clears.
        "personas": ["buyer", "operator", "skeptic", "outsider"],
        "human_question": "Would you, or someone you know, pay for this? Say yes or no, then say who and why.",
    },
    "verified_autonomous": {
        "price_usd": 10.0,
        "claims": [],  # supplied by the audited team; verifier receives claims + invariants, never reasoning
        "personas": ["skeptic", "operator"],
        "human_question": "Does this claim hold, based on what you can see? Yes or no, and what convinced you.",
    },
    "custom": {"price_usd": 8.0, "claims": [], "personas": None, "human_question": None},
}


def default_claims(sku: str) -> list[str]:
    return list(SKUS.get(sku, {}).get("claims", []))


def default_personas(sku: str) -> list[str] | None:
    return SKUS.get(sku, {}).get("personas")


def default_human_question(sku: str) -> str | None:
    return SKUS.get(sku, {}).get("human_question")


def price(sku: str) -> float:
    return float(SKUS.get(sku, {}).get("price_usd", 8.0))
