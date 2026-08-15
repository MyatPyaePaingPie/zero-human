"""SKU presets: which claims and which evaluator personas a product uses.

The router (judge.py) is SKU-agnostic; a SKU is claims + personas + a human question style.
demand_check rubric is the money-swarm demand-to-build gate verbatim; verified_autonomous claims come from the team being audited.
"""
from __future__ import annotations

from reality_check import lenses

SKUS: dict[str, dict] = {
    "reality_check": {
        "price_usd": 8.0,
        "evidence_standard": "human_backed",
        "claims": ["A first-time visitor can tell what this company does within ten seconds"],
        "personas": ["skeptic", "operator", "outsider", "buyer", "designer"],
        "human_question": "After reading this, can you tell what this company does? Say yes or no, then say in one line what you think it does.",
    },
    "demand_check": {
        "price_usd": 10.0,
        "evidence_standard": "human_backed",
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
        "evidence_standard": "human_backed",
        "claims": [],  # supplied by the audited team; verifier receives claims + invariants, never reasoning
        "personas": ["skeptic", "operator"],
        "human_question": "Does this claim hold, based on what you can see? Yes or no, and what convinced you.",
    },
    "custom": {"price_usd": 8.0, "claims": [], "personas": None, "human_question": None},
}

# One intake, every lens. Lenses tag claims so the verdict page groups evidence by question:
# clarity (do strangers get it), demand (money-swarm demand-to-build gate), autonomy (the team's
# own claims, appended at request time), economics (what evidence cost and what the router refused;
# comes from the ledger, not a claim).
_RUBRIC = lenses.claims_for_run()   # single source of truth: reality_check/lenses.py run order

SKUS["full_reality_check"] = {
    "price_usd": 25.0,
    "evidence_standard": "human_backed",
    "claims": [c.text for c, _l, _i in _RUBRIC],
    "lenses": [l for _c, l, _i in _RUBRIC],
    "personas": ["buyer", "operator", "skeptic", "outsider", "designer"],
    "human_question": "Read it as a stranger. For each line say yes or no. Then one sentence: what is this, and would you pay?",
}
LENS_ORDER = ("clarity", "demand", "autonomy", "economics")


def lenses_for(sku: str, n_claims: int) -> list[str]:
    """Lens per claim; claims beyond the preset (team-supplied) are 'autonomy'; single-lens SKUs
    map to their own name."""
    preset = list(SKUS.get(sku, {}).get("lenses") or [])
    single = {"reality_check": "clarity", "demand_check": "demand", "verified_autonomous": "autonomy"}.get(sku)
    out = preset[:n_claims]
    while len(out) < n_claims:
        out.append(single or ("autonomy" if sku == "full_reality_check" else "custom"))
    return out


def default_claims(sku: str) -> list[str]:
    return list(SKUS.get(sku, {}).get("claims", []))


def default_personas(sku: str) -> list[str] | None:
    return SKUS.get(sku, {}).get("personas")


def default_human_question(sku: str) -> str | None:
    return SKUS.get(sku, {}).get("human_question")


def default_standard(sku: str) -> str:
    """Evidence floor sold with the SKU. Room SKUs are human-backed; agent buyers are VOI-routed."""
    return SKUS.get(sku, {}).get("evidence_standard", "voi_routed")


def price(sku: str) -> float:
    return float(SKUS.get(sku, {}).get("price_usd", 8.0))
