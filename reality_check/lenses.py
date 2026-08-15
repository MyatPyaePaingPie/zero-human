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

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Claim:
    text: str
    mode: str = "model"                  # model | objective | both
    human: bool = False
    check: tuple[str, ...] = ()          # finding id prefixes that fail this claim (objective/both)
    slug: str = ""                       # id slug; derived from text when empty (see claim_id)


@dataclass(frozen=True)
class Lens:
    name: str
    title: str
    question: str
    claims: tuple[Claim, ...]
    personas: tuple[str, ...] = ("skeptic", "operator", "outsider")
    human_question: str | None = None
    weight: int = 1                      # stamp weight: 3 = can make the stamp red on its own
    enabled: bool = True                 # False = defined but not in today's run order (issue #18 re-scope)


LENSES: tuple[Lens, ...] = (
    Lens("clarity", "Clarity", "Can a stranger tell what this is in ten seconds?", (
        Claim("A first-time visitor can tell what this product does within ten seconds", "model", human=True, slug="what-it-does"),
        Claim("The headline names who it is for", "model", human=True, slug="who-for"),
        Claim("The headline names a problem the reader already recognizes", "model", human=True, slug="problem-recognized"),
    ), ("outsider", "buyer", "skeptic", "designer"),
       "After reading this, can you tell what this company does? Say yes or no, then say in one line what you think it does.", weight=3),
    Lens("demand", "Demand", "Is there evidence anyone will pay?", (
        Claim("payer: a specific person or role who would pay for this is named", "model", human=True, slug="payer"),
        Claim("painful job: the problem is painful enough that people already spend money or hours on it today", "model", human=True, slug="painful-job"),
        Claim("current workaround or spend: what people do about it today is stated (tool, hire, manual work, or ignore at a cost)", "model", slug="workaround-spend"),
        Claim("reachable audience: the team can reach those people themselves, without a marketplace doing it for them", "model", slug="reachable-audience"),
        Claim("smallest paid test: a paid test could launch in seven days or less", "model", slug="paid-test"),
        Claim("kill rule: there is a stated condition under which the team would kill this", "model", slug="kill-rule"),
    ), ("buyer", "operator", "skeptic", "outsider"),
       "Would you, or someone you know, pay for this? Say yes or no, then say who and why.", weight=3),
    Lens("viability", "Viability", "Do the numbers close?", (
        Claim("A price is stated or unambiguously implied", "model", slug="price-stated"),
        Claim("The cost to serve one customer is stated or inferable from the product", "model", slug="cost-to-serve"),
        Claim("The stated price covers the cost to serve with margin to spare", "model", slug="margin-positive"),
        Claim("The paying segment is reachable through a channel the team names", "model", slug="channel-named"),
    ), ("operator", "buyer", "skeptic"), weight=3),
    Lens("economics", "Economics", "Unit economics, with the assumptions written down.", (
        Claim("The revenue mechanism is named (subscription, usage, one-time, take rate)", "model", slug="revenue-mechanism"),
        Claim("Unit margin is positive at the stated price", "model", slug="unit-margin"),
        Claim("Payback on acquiring a customer is under twelve months at any stated acquisition cost", "model", slug="payback"),
        Claim("The price is defensible against the obvious alternatives", "model", human=True, slug="price-defensible"),
    ), ("operator", "buyer", "skeptic"), "Would you pay the stated price for this? What would you pay?", weight=2, enabled=False),
    Lens("autonomy", "Autonomy", "Does it run without a human in the loop?", (
        Claim("A customer can buy without talking to a human", "both", human=True, check=("autonomy/no-self-serve-buy",), slug="self-serve-buy"),
        Claim("The core loop runs without a human in it", "model", human=True, slug="loop-unattended"),
        Claim("Failures are handled without a human on call", "model", slug="failures-unattended"),
        Claim("Support is not only a human inbox", "both", check=("autonomy/support-mailto-only",), slug="support-not-inbox"),
    ), ("operator", "skeptic"), "Did you need a person to get value from this? Where?", weight=2),
    Lens("stability", "Stability", "Does it stay up and respond?", (
        Claim("The site responds in under three seconds", "objective", check=("live/ttfb-slow",), slug="ttfb"),
        Claim("The homepage returns a successful status", "objective", check=("live/status-error",), slug="status-ok"),
        Claim("The primary user flow completes without a bug (Replay)", "objective", check=("replay/journey-failed",), slug="primary-flow"),
    ), weight=2),
    Lens("security", "Security", "Basic hygiene a buyer's agent would check.", (
        Claim("The site is served over HTTPS only", "objective", check=("live/https-missing",), slug="https"),
        Claim("No secrets or repository internals are exposed", "objective", check=("live/env-exposed", "live/git-exposed"), slug="no-secrets"),
        Claim("Security headers are set (HSTS, CSP, frame protection)", "objective", check=("live/hsts-missing", "live/csp-missing", "live/x-frame-missing"), slug="headers"),
        Claim("Payments are not hand-rolled (a known processor is used)", "both", check=("security/payments-handrolled",), slug="payments-processor"),
    ), weight=2),
    Lens("ux", "UX", "Do the flows actually work?", (
        Claim("Every flow the product claims completes end to end (Replay journeys)", "objective", check=("replay/journey-failed",), slug="flows-complete"),
        Claim("No open UX bugs on the live URL (Replay)", "objective", check=("replay/open-bugs",), slug="no-open-bugs"),
    ), weight=1),
    Lens("accessibility", "Accessibility and performance", "Usable on a phone, by everyone, quickly.", (
        Claim("The page can be zoomed and read on a phone", "objective", check=("audit/viewport-lock",), slug="zoomable"),
        Claim("Images carry alt text and dimensions", "objective", check=("audit/img-alt-missing", "audit/img-dims-missing"), slug="img-alt-dims"),
        Claim("The hero image is not lazy-loaded", "objective", check=("audit/lcp-image-lazy",), slug="lcp-not-lazy"),
        Claim("The page is light enough to load on 4G", "objective", check=("live/heavy-page",), slug="page-weight"),
    ), weight=1),
    Lens("agent_ready", "Agent-ready", "Can agents discover, read, and buy from it? (isitagentready.com)", (
        Claim("Agents can discover the site (robots, sitemap, link headers)", "objective", check=("agentready/discoverability",), slug="discoverability"),
        Claim("Agents can read it (content negotiation)", "objective", check=("agentready/contentAccessibility",), slug="content-access"),
        Claim("Bots are told what they may do", "objective", check=("agentready/botAccessControl",), slug="bot-policy"),
        Claim("Agents can find an API or MCP surface", "objective", check=("agentready/protocolDiscovery",), slug="protocol-discovery"),
        Claim("An agent can pay", "objective", check=("agentready/commerce",), slug="commerce"),
    ), weight=1),
    Lens("seo", "Findability", "Will anyone find it?", (
        Claim("The page can be indexed", "objective", check=("audit/noindex", "audit/robots-missing"), slug="indexable"),
        Claim("The title and description say what it is", "objective", check=("audit/title-missing", "audit/description-missing"), slug="title-description"),
        Claim("The page previews correctly when shared", "objective", check=("audit/og-missing", "audit/twitter-card-no-image"), slug="social-preview"),
        Claim("Search engines get structured data and a canonical URL", "objective", check=("audit/jsonld-missing", "audit/canonical-missing"), slug="structured-data"),
        Claim("There is a sitemap and a crawl policy", "objective", check=("audit/sitemap-missing", "audit/robots-missing", "audit/llms-missing"), slug="sitemap-robots"),
    ), weight=1),
    Lens("competition", "Competition", "Who else, and why you?", (
        Claim("A named alternative exists and the difference is stated", "model", slug="alternative-named"),
        Claim("The difference is one a buyer would pay for", "model", human=True, slug="difference-pays"),
        Claim("The market is not owned by a single incumbent the product cannot displace", "model", slug="no-owner-incumbent"),
    ), ("analyst", "buyer", "skeptic"), "Would you switch from what you use today to this? Why or why not?", weight=2, enabled=False),
    Lens("trust", "Trust", "Real proof or hollow proof?", (
        Claim("The page shows proof a stranger would believe (specific, attributable)", "model", human=True, slug="believable-proof"),
        Claim("Claims of scale are specific, not 'loved by thousands'", "model", slug="specific-scale"),
        Claim("There is a real, reachable person or company behind it", "both", check=("live/contact-missing",), slug="real-person"),
    ), ("skeptic", "outsider", "buyer"), "Do you believe this page? What made you doubt it?", weight=2, enabled=False),
    Lens("legal", "Legal basics", "The boring pages a company must have.", (
        Claim("A privacy policy exists", "objective", check=("live/privacy-missing",), slug="privacy"),
        Claim("Terms of service exist", "objective", check=("live/terms-missing",), slug="terms"),
        Claim("There is a way to contact a human", "objective", check=("live/contact-missing",), slug="contact"),
        Claim("Third-party trackers are not loaded silently", "objective", check=("audit/tracker-undeclared", "audit/google-fonts-cdn"), slug="trackers"),
    ), weight=1),
    Lens("projections", "Projections", "Would this exist in three years?", (
        Claim("There is a stated moat or compounding advantage", "model", slug="moat"),
        Claim("The growth channel does not depend on a platform that can turn it off", "model", slug="channel-independent"),
        Claim("A retention story exists (why customers stay)", "model", slug="retention"),
        Claim("The kill condition is stated", "model", slug="kill-condition"),
    ), ("operator", "analyst", "skeptic"), "Would this exist in three years? Why not?", weight=1, enabled=False),
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


def run_order() -> tuple[Lens, ...]:
    """Today's run order: enabled lenses, in LENS order. Disabled lenses stay defined (the rubric
    is the spec) but nothing evaluates, prices or renders them (issue #18 re-scope, 13:05 PDT)."""
    return tuple(l for l in LENSES if l.enabled)


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    head = text.split(":", 1)[0] if 0 < len(text.split(":", 1)[0]) <= 40 and ":" in text else text
    s = _SLUG_RE.sub("-", head.lower()).strip("-")[:48].strip("-")
    return s or "claim"


def claim_id(lens: str, claim: Claim | str) -> str:
    """Stable `<lens>/<slug>` id. The report (#4) keys findings on it, so it must not drift:
    an explicit Claim.slug pins it when the text is edited."""
    if isinstance(claim, Claim):
        return f"{lens}/{claim.slug or _slug(claim.text)}"
    return f"{lens}/{_slug(claim)}"


def claims_for_run(mode: str | None = None, extra_claims: list[str] | None = None) -> list[tuple[Claim, str, str]]:
    """(claim, lens_name, claim_id) for every claim in today's run order.

    mode filters by claim mode ("model" also yields "both" claims: those are model-judged now and
    overridden by probe evidence later; "objective" yields only pure objective claims)."""
    out: list[tuple[Claim, str, str]] = []
    for lens in run_order():
        for c in lens.claims:
            if mode == "model" and c.mode not in ("model", "both"):
                continue
            if mode == "objective" and c.mode != "objective":
                continue
            out.append((c, lens.name, claim_id(lens.name, c)))
    for i, t in enumerate(extra_claims or []):
        c = Claim(t, "model", human=True, slug=f"team-{i + 1}")
        out.append((c, "autonomy", claim_id("autonomy", c)))
    return out


def personas_for(lens: str) -> list[str]:
    return list(LENS_BY_NAME[lens].personas) if lens in LENS_BY_NAME else ["skeptic", "operator", "outsider"]


def human_question_for(lens: str) -> str | None:
    return LENS_BY_NAME[lens].human_question if lens in LENS_BY_NAME else None
