"""The lens rubric: what a Full Reality Check checks, as binary claims grouped by lens.

Every claim has a mode:
  model      evaluator personas judge it from the input text (cheap, subjective)
  objective  a probe (probes.py, isitagentready, Replay) decides it; no LLM call
  both       probe evidence if a URL exists, models otherwise
and a `human` flag: humans are asked this claim (the human layer judges ON TOP of the
agentic result; the rating page shows them the evidence line).

`check` on objective claims is the id prefix of the probe findings that fail it: the claim
passes when no finding with that prefix is present, "no evidence yet" when no probe ran.
Lenses are the run order for the report. LENS_WEIGHT decides the stamp (see report.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Claim:
    text: str
    mode: str = "model"                  # model | objective | both
    human: bool = False
    check: tuple[str, ...] = ()          # finding id prefixes that fail this claim (objective/both)


@dataclass(frozen=True)
class Lens:
    name: str
    title: str
    question: str
    claims: tuple[Claim, ...]
    personas: tuple[str, ...] = ("skeptic", "operator", "outsider")
    human_question: str | None = None
    weight: int = 1                      # stamp weight: 3 = can make the stamp red on its own


LENSES: tuple[Lens, ...] = (
    Lens("clarity", "Clarity", "Can a stranger tell what this is in ten seconds?", (
        Claim("A first-time visitor can tell what this product does within ten seconds", "model", human=True),
        Claim("The headline names who it is for", "model", human=True),
        Claim("The headline names a problem the reader already recognizes", "model", human=True),
    ), ("outsider", "buyer", "skeptic", "designer"),
       "After reading this, can you tell what this company does? Say yes or no, then say in one line what you think it does.", weight=3),
    Lens("demand", "Demand", "Is there evidence anyone will pay?", (
        Claim("payer: a specific person or role who would pay for this is named", "model", human=True),
        Claim("painful job: the problem is painful enough that people already spend money or hours on it today", "model", human=True),
        Claim("current workaround or spend: what people do about it today is stated (tool, hire, manual work, or ignore at a cost)", "model"),
        Claim("reachable audience: the team can reach those people themselves, without a marketplace doing it for them", "model"),
        Claim("smallest paid test: a paid test could launch in seven days or less", "model"),
        Claim("kill rule: there is a stated condition under which the team would kill this", "model"),
    ), ("buyer", "operator", "skeptic", "outsider"),
       "Would you, or someone you know, pay for this? Say yes or no, then say who and why.", weight=3),
    Lens("viability", "Viability", "Do the numbers close?", (
        Claim("A price is stated or unambiguously implied", "model"),
        Claim("The cost to serve one customer is stated or inferable from the product", "model"),
        Claim("The stated price covers the cost to serve with margin to spare", "model"),
        Claim("The paying segment is reachable through a channel the team names", "model"),
    ), ("operator", "buyer", "skeptic"), weight=3),
    Lens("economics", "Economics", "Unit economics, with the assumptions written down.", (
        Claim("The revenue mechanism is named (subscription, usage, one-time, take rate)", "model"),
        Claim("Unit margin is positive at the stated price", "model"),
        Claim("Payback on acquiring a customer is under twelve months at any stated acquisition cost", "model"),
        Claim("The price is defensible against the obvious alternatives", "model", human=True),
    ), ("operator", "buyer", "skeptic"), "Would you pay the stated price for this? What would you pay?", weight=2),
    Lens("autonomy", "Autonomy", "Does it run without a human in the loop?", (
        Claim("A customer can buy without talking to a human", "both", human=True, check=("autonomy/no-self-serve-buy",)),
        Claim("The core loop runs without a human in it", "model", human=True),
        Claim("Failures are handled without a human on call", "model"),
        Claim("Support is not only a human inbox", "both", check=("autonomy/support-mailto-only",)),
    ), ("operator", "skeptic"), "Did you need a person to get value from this? Where?", weight=2),
    Lens("stability", "Stability", "Does it stay up and respond?", (
        Claim("The site responds in under three seconds", "objective", check=("live/ttfb-slow",)),
        Claim("The homepage returns a successful status", "objective", check=("live/status-error",)),
        Claim("The primary user flow completes without a bug (Replay)", "objective", check=("replay/journey-failed",)),
    ), weight=2),
    Lens("security", "Security", "Basic hygiene a buyer's agent would check.", (
        Claim("The site is served over HTTPS only", "objective", check=("live/https-missing",)),
        Claim("No secrets or repository internals are exposed", "objective", check=("live/env-exposed", "live/git-exposed")),
        Claim("Security headers are set (HSTS, CSP, frame protection)", "objective", check=("live/hsts-missing", "live/csp-missing", "live/x-frame-missing")),
        Claim("Payments are not hand-rolled (a known processor is used)", "both", check=("security/payments-handrolled",)),
    ), weight=2),
    Lens("ux", "UX", "Do the flows actually work?", (
        Claim("Every flow the product claims completes end to end (Replay journeys)", "objective", check=("replay/journey-failed",)),
        Claim("No open UX bugs on the live URL (Replay)", "objective", check=("replay/open-bugs",)),
    ), weight=1),
    Lens("accessibility", "Accessibility and performance", "Usable on a phone, by everyone, quickly.", (
        Claim("The page can be zoomed and read on a phone", "objective", check=("audit/viewport-lock",)),
        Claim("Images carry alt text and dimensions", "objective", check=("audit/img-alt-missing", "audit/img-dims-missing")),
        Claim("The hero image is not lazy-loaded", "objective", check=("audit/lcp-image-lazy",)),
        Claim("The page is light enough to load on 4G", "objective", check=("live/heavy-page",)),
    ), weight=1),
    Lens("agent_ready", "Agent-ready", "Can agents discover, read, and buy from it? (isitagentready.com)", (
        Claim("Agents can discover the site (robots, sitemap, link headers)", "objective", check=("agentready/discoverability",)),
        Claim("Agents can read it (content negotiation)", "objective", check=("agentready/contentAccessibility",)),
        Claim("Bots are told what they may do", "objective", check=("agentready/botAccessControl",)),
        Claim("Agents can find an API or MCP surface", "objective", check=("agentready/protocolDiscovery",)),
        Claim("An agent can pay", "objective", check=("agentready/commerce",)),
    ), weight=1),
    Lens("seo", "Findability", "Will anyone find it?", (
        Claim("The page can be indexed", "objective", check=("audit/noindex", "audit/robots-missing")),
        Claim("The title and description say what it is", "objective", check=("audit/title-missing", "audit/description-missing")),
        Claim("The page previews correctly when shared", "objective", check=("audit/og-missing", "audit/twitter-card-no-image")),
        Claim("Search engines get structured data and a canonical URL", "objective", check=("audit/jsonld-missing", "audit/canonical-missing")),
        Claim("There is a sitemap and a crawl policy", "objective", check=("audit/sitemap-missing", "audit/robots-missing", "audit/llms-missing")),
    ), weight=1),
    Lens("competition", "Competition", "Who else, and why you?", (
        Claim("A named alternative exists and the difference is stated", "model"),
        Claim("The difference is one a buyer would pay for", "model", human=True),
        Claim("The market is not owned by a single incumbent the product cannot displace", "model"),
    ), ("analyst", "buyer", "skeptic"), "Would you switch from what you use today to this? Why or why not?", weight=2),
    Lens("trust", "Trust", "Real proof or hollow proof?", (
        Claim("The page shows proof a stranger would believe (specific, attributable)", "model", human=True),
        Claim("Claims of scale are specific, not 'loved by thousands'", "model"),
        Claim("There is a real, reachable person or company behind it", "both", check=("live/contact-missing",)),
    ), ("skeptic", "outsider", "buyer"), "Do you believe this page? What made you doubt it?", weight=2),
    Lens("legal", "Legal basics", "The boring pages a company must have.", (
        Claim("A privacy policy exists", "objective", check=("live/privacy-missing",)),
        Claim("Terms of service exist", "objective", check=("live/terms-missing",)),
        Claim("There is a way to contact a human", "objective", check=("live/contact-missing",)),
        Claim("Third-party trackers are not loaded silently", "objective", check=("audit/tracker-undeclared", "audit/google-fonts-cdn")),
    ), weight=1),
    Lens("projections", "Projections", "Would this exist in three years?", (
        Claim("There is a stated moat or compounding advantage", "model"),
        Claim("The growth channel does not depend on a platform that can turn it off", "model"),
        Claim("A retention story exists (why customers stay)", "model"),
        Claim("The kill condition is stated", "model"),
    ), ("operator", "analyst", "skeptic"), "Would this exist in three years? Why not?", weight=1),
)

LENS_BY_NAME = {l.name: l for l in LENSES}
STAMP_LENSES = ("clarity", "demand", "viability")   # a failing majority here can turn the stamp red alone


def rubric(*, lenses: tuple[str, ...] | None = None, extra_claims: list[str] | None = None) -> list[tuple[Claim, str]]:
    """(claim, lens) pairs in run order. extra_claims are the audited team's own autonomy claims."""
    out: list[tuple[Claim, str]] = []
    for lens in LENSES:
        if lenses and lens.name not in lenses:
            continue
        out.extend((c, lens.name) for c in lens.claims)
    for t in extra_claims or []:
        out.append((Claim(t, "model", human=True), "autonomy"))
    return out


def personas_for(lens: str) -> list[str]:
    return list(LENS_BY_NAME[lens].personas) if lens in LENS_BY_NAME else ["skeptic", "operator", "outsider"]


def human_question_for(lens: str) -> str | None:
    return LENS_BY_NAME[lens].human_question if lens in LENS_BY_NAME else None
