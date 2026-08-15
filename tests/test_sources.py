"""Tests for reality_check.sources (issue #20). All fetches are network-free via injected
fetchers/resolvers."""
from __future__ import annotations

import io
import json

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from reality_check import probes, sources


def _fr(status: int, text: str = "", url: str = "", headers: dict | None = None) -> probes.FetchResult:
    return probes.FetchResult(status=status, headers=headers or {}, text=text, url=url or "http://x", elapsed_ms=1.0)


def _fake_resolver(host: str):
    return ["93.184.216.34"]


def _build_pdf(texts: list[str]) -> bytes:
    writer = PdfWriter()
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    font_ref = writer._add_object(font)
    for txt in texts:
        page = writer.add_blank_page(width=200, height=200)
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 10 100 Td ({txt}) Tj ET".encode())
        ref = writer._add_object(stream)
        page[NameObject("/Contents")] = ref
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})
        })
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# detect()


@pytest.mark.parametrize("s,expected", [
    ("https://github.com/a/b", "repo"),
    ("https://github.com/a/b/tree/main", "repo"),
    ("http://www.github.com/a/b", "repo"),
    ("https://myapp.example", "page"),
    ("https://example.com/deck.pdf", "deck"),
    ("https://docs.google.com/presentation/d/abc123/edit", "deck"),
    ("https://www.canva.com/design/abc/view", "deck"),
    ("https://pitch.com/decks/abc", "deck"),
    ("https://slides.com/user/deck", "deck"),
    ("https://gamma.app/docs/abc", "deck"),
    ("https://docs.google.com/document/d/abc", "page"),
    ("just some pitch text about our startup", "pitch"),
    ("", "pitch"),
])
def test_detect_table(s, expected):
    assert sources.detect(s) == expected


# ---------------------------------------------------------------------------
# read_repo


def test_read_repo_with_readme_and_manifest():
    repo_json = json.dumps({"full_name": "acme/widget", "homepage": "https://widget.example", "description": "a widget"})
    contents_json = json.dumps([{"name": "package.json"}, {"name": "README.md"}])

    def fetcher(url, timeout_s):
        if url == "https://api.github.com/repos/acme/widget":
            return _fr(200, repo_json)
        if url.endswith("/readme"):
            return _fr(200, "# Widget\nSee it live at https://widget.example/live")
        if url.endswith("/contents/"):
            return _fr(200, contents_json)
        if url.endswith("/contents/package.json"):
            return _fr(200, '{"name": "widget"}')
        return _fr(404)

    src = sources.read_repo("https://github.com/acme/widget", fetcher=fetcher, resolver=_fake_resolver)
    assert src.kind == "repo"
    assert "Widget" in src.text
    assert "package.json" in src.meta["manifests"]
    assert '"name": "widget"' in src.text
    assert src.live_url == "https://widget.example"


def test_read_repo_readme_only_shields_links_no_live_url():
    repo_json = json.dumps({"full_name": "acme/widget", "homepage": "", "description": ""})

    def fetcher(url, timeout_s):
        if url == "https://api.github.com/repos/acme/widget":
            return _fr(200, repo_json)
        if url.endswith("/readme"):
            return _fr(200, "![badge](https://img.shields.io/badge/build-passing-green)")
        if url.endswith("/contents/"):
            return _fr(200, "[]")
        return _fr(404)

    src = sources.read_repo("https://github.com/acme/widget", fetcher=fetcher, resolver=_fake_resolver)
    assert src.live_url is None


def test_read_repo_private_404_no_raise():
    def fetcher(url, timeout_s):
        return _fr(404)

    src = sources.read_repo("https://github.com/acme/secret", fetcher=fetcher, resolver=_fake_resolver)
    assert src.text == ""
    assert src.meta["error"] == "private_or_missing"


# ---------------------------------------------------------------------------
# read_page


def test_read_page_strips_scripts_and_returns_title():
    html = (
        "<html><head><title>My  Page</title><script>evil()</script></head>"
        "<body><nav>nav junk</nav><p>Hello world</p><footer>footer junk</footer></body></html>"
    )

    def fetcher(url, timeout_s):
        return _fr(200, html)

    src = sources.read_page("https://myapp.example", fetcher=fetcher, resolver=_fake_resolver)
    assert "evil()" not in src.text
    assert "nav junk" not in src.text
    assert "footer junk" not in src.text
    assert "Hello world" in src.text
    assert src.meta["title"] == "My Page"
    assert src.live_url == "https://myapp.example"


# ---------------------------------------------------------------------------
# read_deck


def test_read_deck_slide_markers_and_page_count():
    pdf_bytes = _build_pdf(["intro slide", "second slide"])

    def fetcher(url, timeout_s):
        return _fr(200, pdf_bytes.decode("latin-1"))

    src = sources.read_deck("https://example.com/deck.pdf", fetcher=fetcher, resolver=_fake_resolver)
    assert "--- slide 1 ---" in src.text
    assert "--- slide 2 ---" in src.text
    assert src.meta["slides"] == 2


def test_read_deck_with_live_url_in_text():
    pdf_bytes = _build_pdf(["welcome", "try it at https://myapp.example now"])

    def fetcher(url, timeout_s):
        return _fr(200, pdf_bytes.decode("latin-1"))

    src = sources.read_deck("https://example.com/deck.pdf", fetcher=fetcher, resolver=_fake_resolver)
    assert src.live_url == "https://myapp.example"


def test_read_deck_bytes_input():
    pdf_bytes = _build_pdf(["only slide"])
    src = sources.read_deck(pdf_bytes)
    assert src.ref == "pasted"
    assert src.meta["slides"] == 1


def test_read_deck_unreadable_sets_error():
    def fetcher(url, timeout_s):
        return _fr(200, "not a pdf at all")

    src = sources.read_deck("https://canva.com/design/xyz/view", fetcher=fetcher, resolver=_fake_resolver)
    assert src.text == ""
    assert src.meta.get("error", "").startswith("deck_not_readable")


# ---------------------------------------------------------------------------
# normalize


def test_normalize_all_three_sources_markers_in_order():
    repo_json = json.dumps({"full_name": "acme/widget", "homepage": "", "description": ""})
    pdf_bytes = _build_pdf(["deck slide"])

    def fetcher(url, timeout_s):
        if url == "https://api.github.com/repos/acme/widget":
            return _fr(200, repo_json)
        if url.endswith("/readme"):
            return _fr(200, "readme text")
        if url.endswith("/contents/"):
            return _fr(200, "[]")
        if url == "https://myapp.example":
            return _fr(200, "<html><head><title>App</title></head><body>hi</body></html>")
        if url == "https://example.com/deck.pdf":
            return _fr(200, pdf_bytes.decode("latin-1"))
        return _fr(404)

    result = sources.normalize(
        repo="https://github.com/acme/widget",
        page="https://myapp.example",
        deck="https://example.com/deck.pdf",
        fetcher=fetcher,
        resolver=_fake_resolver,
    )
    text = result["text"]
    assert text.index("=== REPO") < text.index("=== PAGE") < text.index("=== DECK")
    assert result["source_kinds"] == ["repo", "page", "deck"]
    assert result["live_url"] == "https://myapp.example"
    assert len(result["sources"]) == 3


def test_normalize_ssrf_blocks_localhost_no_fetch_call():
    called = {"n": 0}

    def fetcher(url, timeout_s):
        called["n"] += 1
        return _fr(200, "should never happen")

    result = sources.normalize(page="http://127.0.0.1", fetcher=fetcher, resolver=_fake_resolver)
    assert called["n"] == 0
    assert any("blocked_host" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# one_box


def test_one_box_pitch_text():
    result = sources.one_box("We are building an AI scheduling assistant for freelancers.")
    assert result["primary_kind"] == "pitch"
    assert result["source_kinds"] == ["pitch"]
    assert "We are building" in result["text"]


def test_judge_accepts_repo_and_deck_and_merges_sources(monkeypatch):
    """#20 wiring: POST /judge with repo+deck (no input) normalizes, stores source_kinds, sets url."""
    from fastapi.testclient import TestClient
    from reality_check import judge as judge_module
    from reality_check import sources as sources_module
    from reality_check.api import app

    def fake_normalize(**kw):
        return {"text": "=== REPO x ===\nREADME says: rockets for hobbyists\n=== DECK y ===\n--- slide 1 ---\nAcme", "live_url": "https://acme.example",
                "source_kinds": ["repo", "deck"], "primary_kind": "repo", "warnings": [],
                "sources": [{"kind": "repo", "ref": kw.get("repo"), "text": "README...", "live_url": None, "meta": {}},
                            {"kind": "deck", "ref": kw.get("deck"), "text": "slides", "live_url": "https://acme.example", "meta": {"slides": 1}}]}
    monkeypatch.setattr(sources_module, "normalize", fake_normalize)
    monkeypatch.setattr(judge_module, "_launch_probes", lambda job_id, url: None)
    c = TestClient(app)
    r = c.post("/judge", json={"repo": "https://github.com/acme/rockets", "deck": "https://docs.google.com/presentation/d/abc/edit",
                               "sku": "reality_check", "evidence_standard": "voi_routed", "max_budget_usd": 0})
    assert r.status_code == 200, r.text
    from reality_check import store
    job = store.get_job(r.json()["job_id"])
    assert job["state"]["sources"]["source_kinds"] == ["repo", "deck"]
    assert job["request"]["url"] == "https://acme.example"
    assert "README says" in job["request"]["input"]
    r2 = c.post("/judge", json={"sku": "reality_check"})
    assert r2.status_code == 422


def test_read_repo_includes_tree_and_guardrail_docstrings():
    """Autonomy grading needs the repo's real safeguards: file names + first docstring lines of
    policy/envelope/webhook/... modules land in the bundle text."""
    from reality_check import sources, probes
    root = "https://api.github.com/repos/acme/rockets"
    pages = {
        root: (200, '{"name":"rockets","full_name":"acme/rockets","homepage":"","description":"x"}'),
        root + "/readme": (200, "# Rockets\nWe sell rockets."),
        root + "/contents/": (200, "[]"),
        root + "/git/trees/HEAD?recursive=1": (200, '{"tree":[{"path":"app/policy/envelope.py","type":"blob"},{"path":"main.py","type":"blob"},{"path":"node_modules/x.js","type":"blob"}]}'),
        root + "/contents/app/policy/envelope.py": (200, '"""Signed spend envelope: caps the agent cannot edit."""\nX=1'),
        root + "/contents/main.py": (200, '# entrypoint\nprint(1)'),
    }

    def fetcher(url, timeout):
        st, body = pages.get(url, (404, "nope"))
        return probes.FetchResult(status=st, headers={"content-type": "application/json"}, text=body, url=url, elapsed_ms=1)

    src = sources.read_repo("https://github.com/acme/rockets", fetcher=fetcher, resolver=lambda h: ["140.82.112.3"])
    assert "app/policy/envelope.py" in src.text and "node_modules" not in src.text
    assert "Signed spend envelope" in src.text
    assert src.meta.get("files") == 2
