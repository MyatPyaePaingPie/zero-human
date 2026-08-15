"""Objective probes against a LIVE URL (issue #3): fetch the real HTML and run regex-level
checks ported from CodingVault/site-spec `packages/core/src/audit/audit.ts` (546 lines, 26
named checks), keeping the SAME check ids so findings are stable across tools. Live-only
checks (prefix `live/`) add things a static file map can never answer: TLS, TTFB, security
headers, exposed secrets, and page-presence for privacy/terms/contact/pricing/support.

Agent-readiness (issue #7) is a second, independent evidence source: POST to
isitagentready.com and fold `failing` categories into findings with prefix `agentready/`.
Fails closed (any error -> agentready: None, no findings) — never blocks the rest of the run.

Ported from audit.ts (site is fetched live, so file-map-only checks cannot run):
  audit/title-missing, audit/description-missing, audit/canonical-missing, audit/jsonld-missing,
  audit/jsonld-invalid, audit/og-missing, audit/twitter-card-no-image, audit/noindex,
  audit/h1-count, audit/img-alt-missing, audit/img-dims-missing, audit/lcp-image-lazy,
  audit/inline-handler, audit/mixed-content, audit/broken-link, audit/robots-missing,
  audit/sitemap-missing, audit/llms-missing, audit/404-missing (soft-404 heuristic),
  audit/viewport-lock, audit/google-fonts-cdn, audit/robots-blocks-ai-search,
  audit/robots-stale-token, audit/tracker-undeclared, audit/cookie-undeclared.

Skipped (need a static file map or a Brief/foundation.json this probe never has):
  audit/foundation-invalid, audit/no-pages          - foundation.json / whole-dir concepts
  audit/sitemap-page-missing, audit/dangling-ref     - need the full built file map
  audit/headers-stale, audit/csp-report-only-theater,
  audit/hsts-preload, audit/cache-policy-missing     - inspect the static _headers file, not
                                                        live response headers (see live/* below)
  audit/headers-missing                              - reinterpreted live as live/hsts-missing,
                                                        live/csp-missing, live/x-frame-missing
  audit/claims-parity                                - needs a Brief to trace facts to
  audit/form-untyped                                 - needs foundation.json form contracts
  audit/jsonld-self-serving-rating                    - not requested by issue #3; out of scope

Live-only additions: live/https-missing, live/ttfb-slow, live/hsts-missing, live/csp-missing,
live/x-frame-missing, live/env-exposed, live/git-exposed, live/status-error, live/privacy-missing,
live/terms-missing, live/contact-missing, live/pricing-missing, live/support-missing.

SSRF guard: scheme must be http/https; every hostname (root fetch AND each manually-followed
redirect hop, max 5) is resolved and rejected if it lands in a private/loopback/link-local/ULA
range or is the literal string "localhost". Rejected -> {"ok": False, "error": "blocked_host"},
no fetch is made. The fetcher (network) and the resolver (DNS) are both injectable so tests never
touch the network.
"""
from __future__ import annotations

import ipaddress
import random
import re
import socket
import string
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx

from reality_check import agentready

MAX_REDIRECTS = 5
DEFAULT_TIMEOUT = 8.0
TTFB_SLOW_MS = 2500.0
HEAVY_PAGE_BYTES = 2_000_000

# CGNAT / shared address space (RFC 6598): not marked private by ipaddress on all Python
# versions, and a real SSRF target on cloud hosts that route it internally.
_EXTRA_BLOCKED_NETS = [ipaddress.ip_network("100.64.0.0/10")]


class BlockedHostError(Exception):
    pass


@dataclass
class FetchResult:
    status: int
    headers: dict[str, str]
    text: str
    url: str
    elapsed_ms: float


Fetcher = Callable[[str, float], FetchResult]
Resolver = Callable[[str], list[str]]


def _default_resolve(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, None)
    return sorted({ai[4][0] for ai in infos})


def _parse_ip_loose(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Accept both strict notation and the classic SSRF-bypass obfuscations of an IPv4 literal:
    decimal (2130706433), hex (0x7f000001), and shorthand dotted (127.1) all mean 127.0.0.1."""
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass
    try:
        return ipaddress.IPv4Address(socket.inet_aton(host))
    except (OSError, ValueError):
        return None


def _ip_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    # IPv4-mapped IPv6 (::ffff:127.0.0.1) must be judged as the IPv4 address it carries, not
    # as an opaque IPv6 literal that never matches an IPv4Network.
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
        return True
    return any(ip in net for net in _EXTRA_BLOCKED_NETS)


def _host_blocked(host: str, resolver: Resolver) -> bool:
    if not host or host.lower() == "localhost":
        return True
    literal = _parse_ip_loose(host)
    if literal is not None:
        return _ip_blocked(literal)
    try:
        ips = resolver(host)
    except OSError:
        return True
    if not ips:
        return True
    for ip_str in ips:
        ip = _parse_ip_loose(ip_str)
        if ip is None or _ip_blocked(ip):
            return True
    return False


def _default_fetch(url: str, timeout_s: float) -> FetchResult:
    t0 = time.monotonic()
    with httpx.Client(follow_redirects=False, timeout=timeout_s) as client:
        r = client.get(url, headers={"User-Agent": "reality-check-probe/1.0"})
    return FetchResult(status=r.status_code, headers={k.lower(): v for k, v in r.headers.items()},
                        text=r.text if r.text else "", url=str(r.url), elapsed_ms=(time.monotonic() - t0) * 1000)


def _fetch_checked(url: str, deadline: float, fetcher: Fetcher, resolver: Resolver, hops_left: int = MAX_REDIRECTS) -> FetchResult:
    """deadline is an absolute time.monotonic() timestamp: every hop (including redirects)
    re-resolves and re-checks the host, and gets only the time left before the deadline (never
    the full per-call budget again), so a chain of hops cannot multiply the total wait."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ("http", "https"):
        raise BlockedHostError(url)
    if _host_blocked(parsed.hostname or "", resolver):
        raise BlockedHostError(url)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError(url)
    resp = fetcher(url, min(remaining, DEFAULT_TIMEOUT))
    if resp.status in (301, 302, 303, 307, 308) and hops_left > 0:
        loc = resp.headers.get("location")
        if loc:
            return _fetch_checked(urllib.parse.urljoin(url, loc), deadline, fetcher, resolver, hops_left - 1)
    return resp


def _try_fetch(url: str, deadline: float, fetcher: Fetcher, resolver: Resolver) -> FetchResult | None:
    """Best-effort fetch for auxiliary probes (robots.txt, /.env, ...): blocked or failed -> None."""
    if deadline - time.monotonic() <= 0:
        return None
    try:
        return _fetch_checked(url, deadline, fetcher, resolver)
    except (BlockedHostError, httpx.HTTPError, OSError, TimeoutError):
        return None


# ---------------------------------------------------------------------------
# finding helpers

def _f(id_: str, severity: str, page: str | None, message: str, evidence: str, fix: str | None = None) -> dict[str, Any]:
    return {"id": id_, "severity": severity, "page": page, "message": message, "fix": fix, "evidence": evidence[:300]}


FINDINGS_PER_ID_CAP = 20


def _cap_findings(findings: list[dict[str, Any]], limit: int = FINDINGS_PER_ID_CAP) -> list[dict[str, Any]]:
    """A page with 20k images must not produce 40k findings. Keep the first `limit` per id and
    fold the rest into one summary finding so the count is still visible."""
    by_id: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for f in findings:
        if f["id"] not in by_id:
            by_id[f["id"]] = []
            order.append(f["id"])
        by_id[f["id"]].append(f)
    out: list[dict[str, Any]] = []
    for id_ in order:
        items = by_id[id_]
        out.extend(items[:limit])
        if len(items) > limit:
            out.append(_f(id_, items[0]["severity"], items[0]["page"],
                          f"{len(items)} total findings for {id_} (showing {limit}).", f"count={len(items)}"))
    return out


TRACKER_SIGNATURES = (
    ("google-analytics", re.compile(r"googletagmanager\.com|google-analytics\.com|\bgtag\s*\(")),
    ("segment", re.compile(r"cdn\.segment\.com|analytics\.load\s*\(")),
    ("hotjar", re.compile(r"static\.hotjar\.com|\bhj\s*\(")),
    ("clarity", re.compile(r"clarity\.ms")),
    ("posthog", re.compile(r"posthog\.(com|init)")),
    ("plausible", re.compile(r"plausible\.io/js")),
    ("fathom", re.compile(r"usefathom\.com")),
    ("matomo", re.compile(r"matomo\.js|_paq\b")),
    ("umami", re.compile(r"umami(\.is)?/script\.js|data-website-id")),
    ("meta-pixel", re.compile(r"connect\.facebook\.net|\bfbq\s*\(")),
)

_SCRIPT_RE = re.compile(r"<script\b[^>]*>[\s\S]*?</script>", re.I)
_SCRIPT_CONTENT_RE = re.compile(r"<script\b[^>]*>([\s\S]*?)</script>", re.I)
_IMG_RE = re.compile(r"<img\b[^>]*>", re.I)
_A_RE = re.compile(r'<a\b[^>]*?\shref="([^"]+)"', re.I)
_ON_ATTR_RE = re.compile(r"<[a-z][^>]*?\s(on[a-z]+)=", re.I)
_LDJSON_RE = re.compile(r'<script type="application/ld\+json">([\s\S]*?)</script>', re.I)
_MIXED_RE = re.compile(r'<(?:link|script|img|source|iframe|video|audio)\b[^>]*?\s(?:href|src)="(http://[^"]+)"', re.I)


def _strip_scripts(html: str) -> str:
    return _SCRIPT_RE.sub("", html)


def _page_checks(html: str, page_url: str, *, is_https: bool) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    p = lambda id_, sev, msg, ev, fix=None: out.append(_f(id_, sev, page_url, msg, ev, fix))
    no_script = _strip_scripts(html)

    if not re.search(r"<title[^>]*>[^<]", html, re.I):
        p("audit/title-missing", "error", "No <title>.", "<title> missing or empty")
    if not re.search(r'<meta\s+name="description"\s+content="[^"]', html, re.I):
        p("audit/description-missing", "error", "No meta description.", "meta[name=description] missing")
    if not re.search(r'rel="canonical"', html, re.I):
        p("audit/canonical-missing", "error", "No canonical URL.", "link[rel=canonical] missing",
          'Add <link rel="canonical">.')
    if not re.search(r"application/ld\+json", html, re.I):
        p("audit/jsonld-missing", "error", "No JSON-LD structured data.", "no ld+json script block")
    if not re.search(r'property="og:title"', html, re.I):
        p("audit/og-missing", "error", "No Open Graph card.", "og:title missing")
    m = re.search(r'<meta[^>]+name="robots"[^>]+content="[^"]*noindex', html, re.I)
    if m:
        p("audit/noindex", "error", "Page is noindexed.", m.group(0)[:200], "Remove noindex unless intentional.")
    h1s = len(re.findall(r"<h1[\s>]", no_script, re.I))
    if h1s != 1:
        p("audit/h1-count", "warning", f"Page has {h1s} <h1> elements (want exactly 1).", f"h1_count={h1s}")

    vp = re.search(r'<meta\s+name="viewport"\s+content="([^"]*)"', html, re.I)
    viewport = vp.group(1) if vp else ""
    if re.search(r"user-scalable\s*=\s*no", viewport, re.I) or re.search(r"maximum-scale\s*=\s*(0|1)(\.\d+)?\b", viewport, re.I):
        p("audit/viewport-lock", "error", f"Viewport blocks zoom ({viewport}).", viewport,
          "Use width=device-width, initial-scale=1 and nothing else.")

    first_img = _IMG_RE.search(no_script)
    if first_img and re.search(r'\sloading="lazy"', first_img.group(0), re.I):
        p("audit/lcp-image-lazy", "warning", "First image on the page is loading=\"lazy\".", first_img.group(0)[:120],
          'Load the hero eagerly with fetchpriority="high".')

    if re.search(r'name="twitter:card"\s+content="summary_large_image"', html, re.I) and not re.search(r'name="twitter:image"', html, re.I):
        p("audit/twitter-card-no-image", "warning", "twitter:card is summary_large_image with no twitter:image.", "twitter:image missing")

    if re.search(r"fonts\.(googleapis|gstatic)\.com", html, re.I):
        p("audit/google-fonts-cdn", "warning", "Fonts load from Google's CDN (shares visitor IPs with Google).",
          "fonts.googleapis.com/gstatic.com reference", "Self-host the woff2 files.")

    for lm in _LDJSON_RE.finditer(html):
        try:
            import json
            json.loads(lm.group(1))
        except ValueError:
            p("audit/jsonld-invalid", "error", "A JSON-LD block is not valid JSON.", lm.group(1)[:150])

    for im in _IMG_RE.finditer(no_script):
        tag = im.group(0)
        if not re.search(r"\salt=", tag, re.I):
            p("audit/img-alt-missing", "error", f"<img> without alt text: {tag[:80]}", tag[:150])
        if not re.search(r"\swidth=", tag, re.I) or not re.search(r"\sheight=", tag, re.I):
            p("audit/img-dims-missing", "warning", f"<img> without width/height: {tag[:80]}", tag[:150])

    for mm in _MIXED_RE.finditer(html):
        p("audit/mixed-content", "error", f"Insecure resource: {mm.group(1)}", mm.group(1), "Serve every subresource over https.")
    for om in _ON_ATTR_RE.finditer(no_script):
        p("audit/inline-handler", "warning", f"Inline event handler ({om.group(1)}).", om.group(0)[:100])
    return out


def _links(html: str, base_url: str) -> list[str]:
    origin = urllib.parse.urlsplit(base_url)
    out: list[str] = []
    seen: set[str] = set()
    for m in _A_RE.finditer(_strip_scripts(html)):
        href = m.group(1)
        if href.startswith(("mailto:", "tel:", "sms:", "javascript:", "#", "data:")):
            continue
        abs_url = urllib.parse.urljoin(base_url, href)
        parsed = urllib.parse.urlsplit(abs_url)
        if parsed.netloc != origin.netloc or parsed.scheme not in ("http", "https"):
            continue
        clean = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))
        if clean not in seen:
            seen.add(clean)
            out.append(clean)
    return out


def _link_matches(html: str, keywords: tuple[str, ...]) -> bool:
    for m in _A_RE.finditer(html):
        href = m.group(1).lower()
        # crude anchor text: everything between this <a ...> and the next </a>
        start = m.end()
        end = html.find("</a>", start)
        text = html[start:end if end != -1 else start + 200].lower()
        if any(k in href or k in text for k in keywords):
            return True
    return False


PRIVACY_KEYWORDS = ("privacy",)
TERMS_KEYWORDS = ("terms", "tos")
CONTACT_KEYWORDS = ("contact", "mailto:")
PRICING_KEYWORDS = ("pricing", "buy", "checkout", "signup", "sign-up", "sign up")
SUPPORT_KEYWORDS = ("support", "help", "mailto:", "chat")


def run(url: str, *, max_pages: int = 5, budget_s: float = 10.0,
        fetcher: Fetcher | None = None, resolver: Resolver | None = None,
        agentready_poster: Callable[[str, float], Any] | None = None) -> dict[str, Any]:
    fetcher = fetcher or _default_fetch
    resolver = resolver or _default_resolve
    result: dict[str, Any] = {"url": url, "ok": True, "fetched": False, "pages": [], "findings": [],
                               "ttfb_ms": None, "status": None, "agentready": None, "namespaces": [],
                               "skipped": ["audit/foundation-invalid", "audit/no-pages", "audit/sitemap-page-missing",
                                           "audit/dangling-ref", "audit/headers-stale", "audit/csp-report-only-theater",
                                           "audit/hsts-preload", "audit/cache-policy-missing", "audit/headers-missing",
                                           "audit/claims-parity", "audit/form-untyped", "audit/jsonld-self-serving-rating"],
                               "error": None}

    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or _host_blocked(parsed.hostname, resolver):
        result["ok"] = False
        result["error"] = "blocked_host"
        return result

    deadline = time.monotonic() + budget_s

    def remaining() -> float:
        return max(0.0, deadline - time.monotonic())

    result["unknown"] = []

    try:
        root = _fetch_checked(url, deadline, fetcher, resolver)
    except BlockedHostError:
        result["ok"] = False
        result["error"] = "blocked_host"
        return result
    except (TimeoutError, httpx.TimeoutException):
        result["error"] = "timeout"
        return result
    except Exception:
        result["error"] = "fetch_error"
        return result

    result["fetched"] = True
    result["status"] = root.status
    result["ttfb_ms"] = round(root.elapsed_ms, 1)
    result["namespaces"] = ["audit", "live"]  # both namespaces always run once we have a root fetch
    is_https = urllib.parse.urlsplit(root.url).scheme == "https"
    findings: list[dict[str, Any]] = []

    if not (200 <= root.status < 400):
        findings.append(_f("live/status-error", "error", root.url, f"Homepage returned status {root.status}.", str(root.status)))
    if not is_https:
        findings.append(_f("live/https-missing", "error", root.url, "Site is not served over HTTPS.", root.url))
    if root.elapsed_ms > TTFB_SLOW_MS:
        findings.append(_f("live/ttfb-slow", "warning", root.url, f"TTFB {root.elapsed_ms:.0f}ms > {TTFB_SLOW_MS:.0f}ms.", f"{root.elapsed_ms:.0f}ms"))
    if len(root.text.encode("utf-8", "ignore")) > HEAVY_PAGE_BYTES:
        findings.append(_f("live/heavy-page", "warning", root.url, "Homepage body exceeds 2MB.", f"{len(root.text)} bytes"))

    hdrs = root.headers
    if is_https and "strict-transport-security" not in hdrs:
        findings.append(_f("live/hsts-missing", "warning", root.url, "No Strict-Transport-Security header.", "no HSTS header"))
    if "content-security-policy" not in hdrs:
        findings.append(_f("live/csp-missing", "warning", root.url, "No Content-Security-Policy header.", "no CSP header"))
    if "x-frame-options" not in hdrs and "frame-ancestors" not in hdrs.get("content-security-policy", ""):
        findings.append(_f("live/x-frame-missing", "warning", root.url, "No X-Frame-Options / frame-ancestors.", "no frame protection header"))

    # per-page checks: root + up to max_pages-1 more same-origin pages
    pages_done = [root.url]
    findings.extend(_page_checks(root.text, root.url, is_https=is_https))

    all_links = _links(root.text, root.url)
    for link in all_links:
        if len(pages_done) >= max_pages or remaining() <= 0.3:
            break
        r2 = _try_fetch(link, deadline, fetcher, resolver)
        if r2 and r2.text and 200 <= r2.status < 400:
            pages_done.append(link)
            findings.extend(_page_checks(r2.text, link, is_https=is_https))
    result["pages"] = pages_done

    # broken links: up to 10 same-origin links from the root page. A real >=400 response is
    # "broken"; no response at all (budget exhausted, blocked, network error) is UNKNOWN, not
    # broken -- fabricating a failing finding out of "we never got to check" is its own bug.
    checked_links = all_links[:10]
    for i, link in enumerate(checked_links):
        if remaining() <= 0.3:
            result["unknown"].append(f"audit/broken-link: budget exhausted, {len(checked_links) - i} link(s) unchecked")
            break
        r2 = _try_fetch(link, deadline, fetcher, resolver)
        if r2 is None:
            result["unknown"].append(f"audit/broken-link: no response for {link}")
            continue
        if r2.status >= 400:
            findings.append(_f("audit/broken-link", "error", root.url, f"Internal link to {link} did not resolve.", str(r2.status)))

    origin = urllib.parse.urlsplit(root.url)
    base = f"{origin.scheme}://{origin.netloc}"

    def aux(path: str) -> FetchResult | None:
        if remaining() <= 0.3:
            return None
        return _try_fetch(base + path, deadline, fetcher, resolver)

    def presence_check(path: str, id_: str, severity: str, message: str, evidence_no_response: str) -> FetchResult | None:
        """A 'missing' finding requires a real HTTP response confirming absence (e.g. 404).
        No response at all (budget/blocked/error) means we don't know -> record unknown, no finding."""
        resp = aux(path)
        if resp is None:
            result["unknown"].append(f"{id_}: no response within budget")
            return None
        if resp.status != 200:
            findings.append(_f(id_, severity, root.url, message, str(resp.status)))
            return None
        return resp

    robots = presence_check("/robots.txt", "audit/robots-missing", "error", "No robots.txt.", "no response")
    if robots is not None:
        for stale in ("anthropic-ai", "Claude-Web"):
            if re.search(rf"^User-agent:\s*{re.escape(stale)}\s*$", robots.text, re.I | re.M):
                findings.append(_f("audit/robots-stale-token", "warning", root.url, f'robots.txt names the deprecated token "{stale}".', stale))
        for bot in ("OAI-SearchBot", "ChatGPT-User", "Claude-User", "Claude-SearchBot", "PerplexityBot", "Perplexity-User"):
            if re.search(rf"User-agent:\s*{re.escape(bot)}\s*\nDisallow:\s*/\s*$", robots.text, re.I | re.M):
                findings.append(_f("audit/robots-blocks-ai-search", "warning", root.url, f"robots.txt blocks {bot}.", bot))

    presence_check("/sitemap.xml", "audit/sitemap-missing", "error", "No sitemap.xml.", "no response")
    presence_check("/llms.txt", "audit/llms-missing", "warning", "No llms.txt.", "no response")

    envf = aux("/.env")
    if envf is None:
        result["unknown"].append("live/env-exposed: no response within budget")
    elif envf.status == 200 and "=" in envf.text:
        findings.append(_f("live/env-exposed", "error", base + "/.env", "GET /.env returned 200 with key=value content.", envf.text[:120]))

    gitf = aux("/.git/HEAD")
    if gitf is None:
        result["unknown"].append("live/git-exposed: no response within budget")
    elif gitf.status == 200 and gitf.text.strip().startswith("ref:"):
        findings.append(_f("live/git-exposed", "error", base + "/.git/HEAD", "GET /.git/HEAD is exposed.", gitf.text[:80]))

    rand_path = "/__reality_check_probe_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=16))
    soft404 = aux(rand_path)
    if soft404 is not None and soft404.status == 200:
        findings.append(_f("audit/404-missing", "warning", root.url, "A random nonexistent path returned 200 (soft 404).", rand_path))
    elif soft404 is None:
        result["unknown"].append("audit/404-missing: no response within budget")

    if not _link_matches(root.text, PRIVACY_KEYWORDS):
        presence_check("/privacy", "live/privacy-missing", "error", "No privacy policy link or page found.", "no response")
    if not _link_matches(root.text, TERMS_KEYWORDS):
        presence_check("/terms", "live/terms-missing", "error", "No terms of service link or page found.", "no response")
    if not _link_matches(root.text, CONTACT_KEYWORDS):
        presence_check("/contact", "live/contact-missing", "warning", "No contact link or page found.", "no response")
    if not _link_matches(root.text, PRICING_KEYWORDS):
        findings.append(_f("live/pricing-missing", "warning", root.url, "No pricing/buy/checkout/signup link found.", "no matching link"))
    if not _link_matches(root.text, SUPPORT_KEYWORDS):
        findings.append(_f("live/support-missing", "warning", root.url, "No support/help/email/chat link found.", "no matching link"))

    # trackers / cookies: signature present with no privacy page link
    has_privacy_link = _link_matches(root.text, PRIVACY_KEYWORDS)
    script_corpus = "\n".join(m.group(1) for m in _SCRIPT_CONTENT_RE.finditer(root.text))
    if not has_privacy_link:
        for tid, pattern in TRACKER_SIGNATURES:
            if pattern.search(root.text) or pattern.search(script_corpus):
                findings.append(_f("audit/tracker-undeclared", "error", root.url, f"Detected {tid} with no privacy page link.", tid))
                break
        if re.search(r"document\.cookie\s*=", script_corpus):
            findings.append(_f("audit/cookie-undeclared", "error", root.url, "Scripts write document.cookie with no privacy page link.", "document.cookie ="))

    if remaining() > 0.5:
        ar_result, ar_findings = agentready.scan(url, poster=agentready_poster, timeout_s=remaining())
        result["agentready"] = ar_result
        if ar_result is not None:
            result["namespaces"].append("agentready")
        findings.extend(ar_findings)
    else:
        result["unknown"].append("agentready: budget exhausted")

    result["findings"] = _cap_findings(findings)

    return result
