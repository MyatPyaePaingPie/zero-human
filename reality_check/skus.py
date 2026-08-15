"""SKU presets: which claims and which evaluator personas a product uses.

The router (judge.py) is SKU-agnostic; a SKU is claims + personas + a human question style.
demand_check rubric text is a placeholder until the money-swarm session sends the exact
demand-to-build gate wording; verified_autonomous claims come from the team being audited.
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
            "There is a specific person or role who would pay for this, and the page names them",
            "The problem it solves is painful enough that people already spend money or hours on it today",
            "The team can reach that audience without a marketplace doing it for them",
            "Someone outside the team would pay for this today, not just say it is cool",
            "There is a stated condition under which the team would kill this idea",
        ],
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
