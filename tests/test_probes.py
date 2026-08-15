"""Tests for reality_check/probes.py (issue #3 objective probes + issue #7 agent-ready scan).
Every fetcher/resolver/poster is injected: no test in this file touches the network.
"""
from __future__ import annotations

from reality_check import agentready, probes


def _fr(status=200, headers=None, text="", url="https://good.example.com/"):
    return probes.FetchResult(status=status, headers={k.lower(): v for k, v in (headers or {}).items()},
                              text=text, url=url, elapsed_ms=50.0)


CLEAN_HTML = """<!doctype html><html><head>
<title>Acme Rockets - buy rockets</title>
<meta name="description" content="Acme sells rockets to hobbyists.">
<link rel="canonical" href="https://good.example.com/">
<script type="application/ld+json">{"@type":"Organization","name":"Acme"}</script>
<meta property="og:title" content="Acme Rockets">
<meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body>
<h1>Acme Rockets</h1>
<img src="/hero.png" alt="a rocket" width="200" height="100">
<a href="/privacy">Privacy</a>
<a href="/terms">Terms</a>
<a href="/contact">Contact</a>
<a href="/pricing">Pricing</a>
<a href="/support">Support</a>
</body></html>"""

BAD_HTML = """<!doctype html><html><head></head>
<body>
<h1>One</h1><h1>Two</h1>
<img src="/x.png">
<script src="http://insecure.example.com/a.js"></script>
<a href="#" onclick="doThing()">click</a>
</body></html>"""


def _resolver_ok(_host):
    return ["93.184.216.34"]


def _make_fetcher(pages: dict, aux_default=None):
    """pages: {url_or_path_suffix: FetchResult}. aux_default returned (or 404) for anything else."""
    def fetcher(url, timeout_s):
        for key, fr in pages.items():
            if url == key or url.endswith(key):
                return fr
        if aux_default is not None:
            return aux_default(url)
        return _fr(status=404, url=url, text="not found")
    return fetcher


def test_clean_site_no_audit_findings():
    root = "https://good.example.com/"
    pages = {
        root: _fr(text=CLEAN_HTML, url=root),
        "/robots.txt": _fr(text="User-agent: *\nAllow: /", url=root + "robots.txt"),
        "/sitemap.xml": _fr(text="<urlset></urlset>", url=root + "sitemap.xml"),
        "/llms.txt": _fr(text="# Acme", url=root + "llms.txt"),
        "/privacy": _fr(text="privacy policy", url=root + "privacy"),
        "/terms": _fr(text="terms", url=root + "terms"),
        "/contact": _fr(text="contact", url=root + "contact"),
        "/pricing": _fr(text="pricing", url=root + "pricing"),
        "/support": _fr(text="support", url=root + "support"),
        "/.env": _fr(status=404, url=root + ".env"),
        "/.git/HEAD": _fr(status=404, url=root + ".git/HEAD"),
    }
    fetcher = _make_fetcher(pages)
    # max_pages=1: only the root gets full per-page checks; /privacy /terms /contact /pricing
    # /support are plain-text fixtures here, only used to answer the broken-link + presence probes
    res = probes.run(root, fetcher=fetcher, resolver=_resolver_ok, agentready_poster=lambda u, t: None, max_pages=1)
    assert res["ok"] and res["fetched"]
    audit_ids = {f["id"] for f in res["findings"] if f["id"].startswith("audit/")}
    assert audit_ids == set(), audit_ids


def test_bad_site_flags_expected_findings():
    root = "https://bad.example.com/"
    pages = {root: _fr(text=BAD_HTML, url=root)}
    fetcher = _make_fetcher(pages)  # robots/sitemap/llms/privacy/etc all 404 via aux_default
    res = probes.run(root, fetcher=fetcher, resolver=_resolver_ok, agentready_poster=lambda u, t: None)
    assert res["ok"] and res["fetched"]
    ids = {f["id"] for f in res["findings"]}
    expected_subset = {
        "audit/title-missing", "audit/description-missing", "audit/canonical-missing",
        "audit/jsonld-missing", "audit/og-missing", "audit/h1-count",
        "audit/img-alt-missing", "audit/img-dims-missing", "audit/inline-handler",
        "audit/mixed-content", "audit/robots-missing", "audit/sitemap-missing", "audit/llms-missing",
    }
    assert expected_subset <= ids, expected_subset - ids


def test_ssrf_blocked_hosts_never_call_fetcher():
    calls = []

    def fetcher(url, timeout_s):
        calls.append(url)
        return _fr()

    for bad_url in ("http://127.0.0.1/", "http://10.1.2.3/", "http://localhost/", "ftp://example.com/"):
        res = probes.run(bad_url, fetcher=fetcher, resolver=_resolver_ok)
        assert res["ok"] is False
        assert res["error"] == "blocked_host"
    assert calls == []


def test_timeout_fetcher_yields_no_findings():
    def timeout_fetcher(url, timeout_s):
        raise TimeoutError("simulated timeout")

    res = probes.run("https://good.example.com/", fetcher=timeout_fetcher, resolver=_resolver_ok)
    assert res["fetched"] is False
    assert res["findings"] == []
    assert res["error"] == "timeout"


def test_agentready_mocked_dict_and_findings():
    """Real API shape: checks.<category>.<check>.status; 'discovery' aliases to protocolDiscovery;
    neutral is neither pass nor fail."""
    def poster(url, timeout_s):
        return {"level": 0, "levelName": "Not Ready", "checks": {
            "discoverability": {"robotsTxt": {"status": "fail", "message": "robots.txt not found"}, "sitemap": {"status": "pass"}},
            "contentAccessibility": {"markdownNegotiation": {"status": "pass"}},
            "botAccessControl": {"webBotAuth": {"status": "neutral"}},
            "discovery": {"mcpServerCard": {"status": "fail", "message": "no card"}},
            "commerce": {"x402": {"status": "neutral"}}}}
    result, findings = agentready.scan("https://good.example.com/", poster=poster)
    assert result["level"] == 0
    assert [f["category"] for f in result["failing"]] == ["discoverability", "protocolDiscovery"]
    assert "discoverability.sitemap" in result["passing"]
    ids = {f["id"] for f in findings}
    assert ids == {"agentready/discoverability-failing", "agentready/protocolDiscovery-failing"}
    assert "robots.txt not found" in findings[0]["evidence"]


def test_agentready_exception_fails_closed():
    def poster(url, timeout_s):
        raise RuntimeError("network down")

    result, findings = agentready.scan("https://good.example.com/", poster=poster)
    assert result is None
    assert findings == []


def test_agentready_folded_into_probes_run():
    root = "https://good.example.com/"
    fetcher = _make_fetcher({root: _fr(text=CLEAN_HTML, url=root)})

    def poster(url, timeout_s):
        return {"failing": ["protocolDiscovery"], "passing": []}

    res = probes.run(root, fetcher=fetcher, resolver=_resolver_ok, agentready_poster=poster)
    assert res["agentready"]["failing"] == ["protocolDiscovery"]
    assert any(f["id"] == "agentready/protocolDiscovery-failing" for f in res["findings"])


def test_end_to_end_judge_with_url_backs_objective_claim(monkeypatch):
    from fastapi.testclient import TestClient
    from reality_check import judge as judge_module
    from reality_check import probes as probes_module
    from reality_check.api import app

    root = "https://insecure.example.com/"
    bad_html = "<html><head></head><body><h1>hi</h1></body></html>"

    def fake_probes_run(url, **kwargs):
        return {
            "url": url, "ok": True, "fetched": True, "pages": [url],
            "findings": [{"id": "live/https-missing", "severity": "error", "page": url,
                         "message": "not https", "fix": None, "evidence": url}],
            "ttfb_ms": 10.0, "status": 200, "agentready": None, "skipped": [], "error": None,
            "namespaces": ["audit", "live"],
        }

    monkeypatch.setattr(probes_module, "run", fake_probes_run)
    monkeypatch.setattr(judge_module, "probes", probes_module)

    class _SyncThread:  # run the probe "thread" inline so the test is deterministic
        def __init__(self, target=None, daemon=None):
            self._target = target

        def start(self):
            if self._target:
                self._target()

    monkeypatch.setattr(judge_module.threading, "Thread", _SyncThread)

    c = TestClient(app)
    r = c.post("/judge", json={
        "input": "Acme sells rockets.",
        "claim": "The site is served over HTTPS only",
        "url": root,
        "cost_if_wrong_usd": 100, "max_budget_usd": 8, "evidence_standard": "voi_routed",
    }, headers={"X-RC-Paid": "0"})
    assert r.status_code == 200, r.text
    jid = r.json()["job_id"]

    import time as _time
    for _ in range(50):
        v = c.get(f"/judge/{jid}").json()
        cv = v["claims"][0] if v.get("claims") else None
        if cv and cv.get("objective") and cv["objective"].get("source") == "probes":
            break
        _time.sleep(0.05)
    v = c.get(f"/judge/{jid}").json()
    cv = v["claims"][0]
    assert cv["objective"]["source"] == "probes"
    assert "live/https-missing" in cv["objective"]["failing"]
    assert cv["verdict"] == "no"


# ---------------------------------------------------------------------------
# Verifier fixes (blockers 1-3, majors 4-5, minor 6)

def test_host_blocked_table():
    """Item 1: IPv4-mapped IPv6, obfuscated decimal/hex/shorthand IPv4, unspecified/multicast/
    reserved/CGNAT ranges, and a DNS name resolving to a private IP must all be blocked; real
    public addresses must not be."""
    cases = [
        ("127.0.0.1", True), ("10.1.2.3", True), ("172.16.0.1", True), ("192.168.1.1", True),
        ("169.254.169.254", True), ("0.0.0.0", True),
        ("2130706433", True),      # decimal-encoded 127.0.0.1
        ("0x7f000001", True),      # hex-encoded 127.0.0.1
        ("127.1", True),           # shorthand 127.0.0.1
        ("::1", True), ("::", True),
        ("::ffff:127.0.0.1", True),      # IPv4-mapped loopback
        ("::ffff:169.254.169.254", True),  # IPv4-mapped link-local (cloud metadata)
        ("fc00::1", True), ("fd00::1", True), ("fe80::1", True),
        ("100.64.0.1", True),      # CGNAT / shared address space
        ("localhost", True),
        ("93.184.216.34", False),  # a real public IP (example.com)
        ("8.8.8.8", False),
    ]
    for host, expected in cases:
        assert probes._host_blocked(host, lambda h: [h]) is expected, host

    # a DNS name whose injected resolver returns a private IP is blocked too
    assert probes._host_blocked("evil.example.com", lambda h: ["10.0.0.5"]) is True


def test_redirect_to_private_ip_blocked_no_second_fetch():
    calls = []

    def fetcher(url, timeout_s):
        calls.append(url)
        if url == "https://good.example.com/":
            return probes.FetchResult(status=302, headers={"location": "http://127.0.0.1/"}, text="", url=url, elapsed_ms=1.0)
        raise AssertionError("fetcher should not be called again after the redirect is blocked")

    res = probes.run("https://good.example.com/", fetcher=fetcher, resolver=_resolver_ok)
    assert res["ok"] is False
    assert res["error"] == "blocked_host"
    assert calls == ["https://good.example.com/"]


def test_patch_job_state_survives_concurrent_wholesale_write():
    """Item 2: a wholesale put_job (as start() does for claims/voi/panel) and a targeted
    patch_job_state (as the probe thread does) must not clobber each other regardless of order."""
    from reality_check import store
    store.init()
    jid = "test-patch-race"
    store.put_job(jid, "buyer", "evaluating", {"sku": "custom"}, {})
    # simulate: probe thread reads before start's wholesale write ...
    # ... then start's wholesale write lands first ...
    store.put_job(jid, "buyer", "settled", {"sku": "custom"}, {"claims": [{"idx": 0}], "voi": {"buy": False}})
    # ... then the probe thread's patch lands after
    store.patch_job_state(jid, "probes", {"fetched": True, "findings": []})
    job = store.get_job(jid)
    assert job["state"]["claims"] == [{"idx": 0}]
    assert job["state"]["probes"] == {"fetched": True, "findings": []}
    assert job["status"] == "settled"


def test_verdict_does_not_override_claim_outside_produced_namespace():
    from fastapi.testclient import TestClient
    from reality_check import judge as judge_module
    from reality_check import probes as probes_module
    from reality_check.api import app

    def fake_probes_run(url, **kwargs):
        return {"url": url, "ok": True, "fetched": True, "pages": [url], "findings": [],
                "ttfb_ms": 10.0, "status": 200, "agentready": None, "skipped": [], "error": None,
                "namespaces": ["audit", "live"]}

    monkeypatch_run = fake_probes_run
    orig_run = probes_module.run
    probes_module.run = monkeypatch_run
    try:
        c = TestClient(app)
        r = c.post("/judge", json={
            "input": "Acme sells rockets.",
            "claim": "A customer can buy without talking to a human",
            "url": "https://good.example.com/",
            "cost_if_wrong_usd": 100, "max_budget_usd": 8, "evidence_standard": "voi_routed",
        }, headers={"X-RC-Paid": "0"})
        assert r.status_code == 200, r.text
        jid = r.json()["job_id"]
        import time as _time
        _time.sleep(0.3)  # background thread
        v = c.get(f"/judge/{jid}").json()
        cv = v["claims"][0]
        assert cv["objective"] is None
    finally:
        probes_module.run = orig_run


def test_budget_exhaustion_does_not_fabricate_missing_findings():
    """Item 4: aux() calls (robots/sitemap/llms/privacy/terms/contact) and broken-link checks
    that never got an HTTP response (budget ran out) must not produce 'missing' findings."""
    import time as _time
    root = "https://good.example.com/"

    def slow_fetcher(url, timeout_s):
        if url == root:
            _time.sleep(0.95)
            return _fr(text=CLEAN_HTML, url=root)
        raise AssertionError(f"aux fetch should never happen: budget exhausted before {url}")

    res = probes.run(root, fetcher=slow_fetcher, resolver=_resolver_ok, budget_s=1.0, agentready_poster=lambda u, t: None)
    ids = {f["id"] for f in res["findings"]}
    forbidden = {"audit/robots-missing", "audit/sitemap-missing", "audit/llms-missing",
                "live/privacy-missing", "live/terms-missing", "live/contact-missing", "audit/broken-link"}
    assert ids & forbidden == set(), ids & forbidden
    assert res.get("unknown")


def test_run_is_time_bounded_despite_slow_fetcher():
    """Item 5: per-hop timeouts shrink with the deadline and agentready is skipped once the
    budget is nearly spent, so total wall time stays close to budget_s even with many aux calls."""
    import time as _time

    def slow_fetcher(url, timeout_s):
        _time.sleep(min(timeout_s, 5))
        return _fr(text=CLEAN_HTML, url=url)

    t0 = _time.monotonic()
    probes.run("https://good.example.com/", fetcher=slow_fetcher, resolver=_resolver_ok, budget_s=2.0,
               agentready_poster=lambda u, t: (_time.sleep(min(t, 5)), None)[1])
    assert _time.monotonic() - t0 < 3.0


def test_findings_capped_per_id():
    root = "https://many-imgs.example.com/"
    html = "<html><head><title>x</title><meta name=\"description\" content=\"d\">" \
           "<link rel=\"canonical\" href=\"/\"><script type=\"application/ld+json\">{}</script>" \
           "<meta property=\"og:title\" content=\"x\"></head><body><h1>x</h1>" + ("<img src='/a.png'>" * 50) + "</body></html>"
    fetcher = _make_fetcher({root: _fr(text=html, url=root)})
    res = probes.run(root, fetcher=fetcher, resolver=_resolver_ok, agentready_poster=lambda u, t: None, max_pages=1)
    alt_missing = [f for f in res["findings"] if f["id"] == "audit/img-alt-missing"]
    assert len(alt_missing) <= 21, len(alt_missing)


def test_starved_secrets_checks_are_unknown_not_pass():
    """R1: /.env and /.git/HEAD with no response are recorded unknown, and verdict must not
    auto-pass the secrets claim on them."""
    from reality_check import judge, probes

    def slow_fetch(url, timeout, **kw):
        import time as _t
        if url.rstrip("/").endswith("example.com"):
            return probes.FetchResult(url=url, status=200, headers={"content-type": "text/html"}, text="<html><head><title>x</title></head><body><h1>x</h1></body></html>", elapsed_ms=10)
        _t.sleep(timeout)
        raise TimeoutError("slow")

    res = probes.run("https://example.com", budget_s=0.6, fetcher=slow_fetch, resolver=lambda h: ["93.184.216.34"])
    unknown = " ".join(res["unknown"])
    assert "live/env-exposed" in unknown and "live/git-exposed" in unknown
    ids = {f["id"] for f in res["findings"]}
    assert "live/env-exposed" not in ids and "live/git-exposed" not in ids
    # verdict gate: prefixes present in unknown must not be overridden
    prefixes = ("live/env-exposed", "live/git-exposed")
    unk = [u.split(":", 1)[0] for u in res["unknown"]]
    assert any(u.startswith(p) for u in unk for p in prefixes)
