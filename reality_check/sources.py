"""Normalize the three intake inputs (issue #20) — a repo URL, a live page URL, and a deck
(PDF, Google Slides link, or Canva/Pitch/Gamma link) — plus optional pasted pitch text, into one
merged text blob with source markers. Any subset may be supplied; whichever were supplied is
recorded in ``source_kinds``. ``live_url`` is picked with precedence: the page URL first, then the
first non-badge http(s) link found in the repo's homepage/README, then the first http(s) link
found in the deck text.

Every network fetch is routed through ``reality_check.probes``' SSRF guard
(``_host_blocked`` / ``_fetch_checked``): scheme must be http/https, hostname is resolved and
rejected if private/loopback/link-local/reserved, and redirects re-check the guard on every hop.
The guard is imported, never duplicated. A blocked or failing fetch never raises out of this
module — it produces a ``Source`` with empty text and a ``meta["error"]``, and a warning is
appended to ``normalize()``'s output. Fetched content is treated strictly as data: nothing in it
is ever interpreted as an instruction to this module or to callers.
"""
from __future__ import annotations

import os
import re
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

import httpx

from reality_check import probes

MAX_TEXT_BYTES = 12_000
MAX_README_BYTES = 20_000
MAX_TREE_PATHS = 300
MAX_MANIFEST_BYTES = 20_000
MAX_DECK_PAGES = 60

MANIFEST_FILES = [
    "package.json", "pyproject.toml", "requirements.txt", "Cargo.toml", "go.mod", "Gemfile",
    "composer.json",
]

DECK_HOSTS = {"canva.com", "pitch.com", "slides.com", "gamma.app"}

_BADGE_HOST_SNIPPETS = ("shields.io", "img.shields.io", "badge.fury.io", "badgen.net")

_GITHUB_RE = re.compile(r"^https?://(?:www\.)?github\.com/([^/\s#?]+)/([^/\s#?]+)", re.I)
_URL_RE = re.compile(r"https?://[^\s\)\]\"'<>]+")


@dataclass
class Source:
    kind: str  # repo | page | deck | pitch
    ref: str  # url or "pasted"
    text: str
    live_url: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "ref": self.ref, "text": self.text, "live_url": self.live_url, "meta": self.meta}


def detect(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return "pitch"
    if _GITHUB_RE.match(s):
        return "repo"
    if s.lower().split("?")[0].split("#")[0].endswith(".pdf"):
        return "deck"
    parsed = urllib.parse.urlsplit(s)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        host = (parsed.hostname or "").lower().removeprefix("www.")
        path = parsed.path.lower()
        if host == "docs.google.com" and path.startswith("/presentation"):
            return "deck"
        if host in DECK_HOSTS or any(host.endswith("." + h) for h in DECK_HOSTS):
            return "deck"
        return "page"
    return "pitch"


def _is_badge_link(url: str) -> bool:
    low = url.lower()
    return any(snippet in low for snippet in _BADGE_HOST_SNIPPETS)


def _first_live_link(text: str) -> str | None:
    for m in _URL_RE.finditer(text or ""):
        url = m.group(0).rstrip(").,]'\"")
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
        if host in ("github.com", "www.github.com"):
            continue
        if _is_badge_link(url):
            continue
        return url
    return None


# ---------------------------------------------------------------------------
# repo


def _gh_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "reality-check-sources/1.0"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _default_get_fetcher(headers: dict[str, str]) -> probes.Fetcher:
    def _fetch(url: str, timeout_s: float) -> probes.FetchResult:
        t0 = time.monotonic()
        with httpx.Client(follow_redirects=False, timeout=timeout_s) as client:
            r = client.get(url, headers=headers)
        return probes.FetchResult(
            status=r.status_code,
            headers={k.lower(): v for k, v in r.headers.items()},
            text=r.text if r.text else "",
            url=str(r.url),
            elapsed_ms=(time.monotonic() - t0) * 1000,
        )
    return _fetch


def _guarded_get(url: str, deadline: float, fetcher: probes.Fetcher | None, resolver: probes.Resolver,
                  headers: dict[str, str] | None = None) -> probes.FetchResult:
    fetch_fn = fetcher or _default_get_fetcher(headers or {})
    return probes._fetch_checked(url, deadline, fetch_fn, resolver)


def read_repo(url: str, *, fetcher: probes.Fetcher | None = None, budget_s: float = 8,
              resolver: probes.Resolver | None = None) -> Source:
    resolver = resolver or probes._default_resolve
    deadline = time.monotonic() + budget_s
    meta: dict[str, Any] = {}
    m = _GITHUB_RE.match(url or "")
    if not m:
        return Source(kind="repo", ref=url, text="", live_url=None, meta={"error": "not_a_github_url"})
    owner, repo = m.group(1), m.group(2)
    if repo.endswith(".git"):
        repo = repo[: -len(".git")]
    headers = _gh_headers()

    try:
        resp = _guarded_get(f"https://api.github.com/repos/{owner}/{repo}", deadline, fetcher, resolver, headers)
    except (probes.BlockedHostError, TimeoutError, httpx.HTTPError, OSError) as e:
        return Source(kind="repo", ref=url, text="", live_url=None, meta={"error": f"repo_fetch_failed:{e}"})

    if resp.status in (404, 403):
        return Source(kind="repo", ref=url, text="", live_url=None, meta={"error": "private_or_missing"})
    if resp.status >= 400:
        return Source(kind="repo", ref=url, text="", live_url=None, meta={"error": f"http_{resp.status}"})

    import json as _json
    try:
        info = _json.loads(resp.text or "{}")
    except ValueError:
        info = {}
    homepage = info.get("homepage") or ""
    description = info.get("description") or ""
    meta["title"] = info.get("full_name") or f"{owner}/{repo}"
    meta["homepage"] = homepage
    meta["description"] = description

    parts = [f"repo: {owner}/{repo}"]
    if description:
        parts.append(f"description: {description}")
    if homepage:
        parts.append(f"homepage: {homepage}")

    # README
    try:
        readme_resp = _guarded_get(
            f"https://api.github.com/repos/{owner}/{repo}/readme", deadline, fetcher, resolver,
            {**headers, "Accept": "application/vnd.github.raw"},
        )
        if readme_resp.status < 400:
            readme_text = (readme_resp.text or "")[:MAX_README_BYTES]
            meta["readme_bytes"] = len(readme_text)
            parts.append("--- README ---\n" + readme_text)
    except (probes.BlockedHostError, TimeoutError, httpx.HTTPError, OSError):
        meta.setdefault("warnings", []).append("readme_fetch_failed")

    # top-level contents -> manifest files
    manifests_found: list[str] = []
    try:
        contents_resp = _guarded_get(
            f"https://api.github.com/repos/{owner}/{repo}/contents/", deadline, fetcher, resolver, headers,
        )
        if contents_resp.status < 400:
            try:
                entries = _json.loads(contents_resp.text or "[]")
            except ValueError:
                entries = []
            names = {e.get("name") for e in entries if isinstance(e, dict)} if isinstance(entries, list) else set()
            for fname in MANIFEST_FILES:
                if fname not in names:
                    continue
                try:
                    mresp = _guarded_get(
                        f"https://api.github.com/repos/{owner}/{repo}/contents/{fname}", deadline, fetcher,
                        resolver, {**headers, "Accept": "application/vnd.github.raw"},
                    )
                except (probes.BlockedHostError, TimeoutError, httpx.HTTPError, OSError):
                    continue
                if mresp.status < 400:
                    mtext = (mresp.text or "")[:MAX_MANIFEST_BYTES]
                    manifests_found.append(fname)
                    parts.append(f"--- {fname} ---\n{mtext}")
    except (probes.BlockedHostError, TimeoutError, httpx.HTTPError, OSError):
        meta.setdefault("warnings", []).append("contents_fetch_failed")

    meta["manifests"] = manifests_found

    # file tree (names only, one call): sponsor evidence often lives in file names and module
    # docstrings, not the README (terac_client.py, stripe_webhook.py); cap so a monorepo stays cheap
    try:
        tree_resp = _guarded_get(
            f"https://api.github.com/repos/{owner}/{repo}/git/trees/HEAD?recursive=1", deadline, fetcher, resolver, headers,
        )
        if tree_resp.status < 400:
            try:
                tree = _json.loads(tree_resp.text or "{}").get("tree") or []
            except ValueError:
                tree = []
            skip = ("node_modules/", ".venv/", "vendor/", "dist/", "build/", ".git/")
            paths = [e.get("path", "") for e in tree if isinstance(e, dict) and e.get("type") == "blob"
                     and not any(e.get("path", "").startswith(sk) or f"/{sk}" in e.get("path", "") for sk in skip)]
            meta["files"] = len(paths)
            if paths:
                parts.append("--- files (top " + str(min(len(paths), MAX_TREE_PATHS)) + ") ---\n" + "\n".join(paths[:MAX_TREE_PATHS]))
    except (probes.BlockedHostError, TimeoutError, httpx.HTTPError, OSError):
        meta.setdefault("warnings", []).append("tree_fetch_failed")

    live_url = None
    for candidate_text in (homepage, "\n".join(p for p in parts if p.startswith("--- README"))):
        found = _first_live_link(candidate_text)
        if found:
            live_url = found
            break

    return Source(kind="repo", ref=url, text="\n\n".join(parts), live_url=live_url, meta=meta)


# ---------------------------------------------------------------------------
# page

_TAG_STRIP_RE = re.compile(r"<(script|style|nav|footer)\b[^>]*>.*?</\1>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_WS_RE = re.compile(r"\s+")


def read_page(url: str, *, fetcher: probes.Fetcher | None = None, budget_s: float = 8,
              resolver: probes.Resolver | None = None) -> Source:
    resolver = resolver or probes._default_resolve
    deadline = time.monotonic() + budget_s
    try:
        resp = _guarded_get(url, deadline, fetcher, resolver, {"User-Agent": "reality-check-sources/1.0"})
    except probes.BlockedHostError:
        return Source(kind="page", ref=url, text="", live_url=None, meta={"error": "blocked_host"})
    except (TimeoutError, httpx.HTTPError, OSError) as e:
        return Source(kind="page", ref=url, text="", live_url=None, meta={"error": f"page_fetch_failed:{e}"})

    if resp.status >= 400:
        return Source(kind="page", ref=url, text="", live_url=None, meta={"error": f"http_{resp.status}"})

    html = resp.text or ""
    title_m = _TITLE_RE.search(html)
    title = _WS_RE.sub(" ", title_m.group(1)).strip() if title_m else ""
    stripped = _TAG_STRIP_RE.sub(" ", html)
    visible = _TAG_RE.sub(" ", stripped)
    visible = _WS_RE.sub(" ", visible).strip()[:MAX_TEXT_BYTES]

    return Source(kind="page", ref=url, text=visible, live_url=url, meta={"title": title})


# ---------------------------------------------------------------------------
# deck

_GOOGLE_SLIDES_RE = re.compile(r"^https?://docs\.google\.com/presentation/d/([^/]+)", re.I)


def _pdf_text(data: bytes) -> tuple[str, int]:
    from pypdf import PdfReader
    import io

    reader = PdfReader(io.BytesIO(data))
    pages = reader.pages[:MAX_DECK_PAGES]
    chunks = []
    for i, page in enumerate(pages, start=1):
        try:
            txt = page.extract_text() or ""
        except Exception:
            txt = ""
        chunks.append(f"--- slide {i} ---\n{txt.strip()}")
    return "\n\n".join(chunks), len(pages)


def read_deck(url_or_bytes: str | bytes, *, fetcher: probes.Fetcher | None = None, budget_s: float = 10,
              resolver: probes.Resolver | None = None) -> Source:
    resolver = resolver or probes._default_resolve

    if isinstance(url_or_bytes, (bytes, bytearray)):
        try:
            text, n = _pdf_text(bytes(url_or_bytes))
        except Exception as e:
            return Source(kind="deck", ref="pasted", text="", live_url=None, meta={"error": f"deck_not_readable:{e}"})
        live_url = _first_live_link(text)
        return Source(kind="deck", ref="pasted", text=text, live_url=live_url, meta={"slides": n})

    url = url_or_bytes
    deadline = time.monotonic() + budget_s
    fetch_url = url
    gs = _GOOGLE_SLIDES_RE.match(url or "")
    if gs:
        fetch_url = f"https://docs.google.com/presentation/d/{gs.group(1)}/export/pdf"

    try:
        resp = _guarded_get(fetch_url, deadline, fetcher, resolver, {"User-Agent": "reality-check-sources/1.0"})
    except probes.BlockedHostError:
        return Source(kind="deck", ref=url, text="", live_url=None, meta={"error": "blocked_host"})
    except (TimeoutError, httpx.HTTPError, OSError) as e:
        return Source(kind="deck", ref=url, text="", live_url=None, meta={"error": f"deck_fetch_failed:{e}"})

    if resp.status >= 400:
        return Source(kind="deck", ref=url, text="", live_url=None, meta={"error": f"deck_not_readable:http_{resp.status}"})

    raw = (resp.text or "")
    data = raw.encode("latin-1", errors="ignore") if isinstance(raw, str) else raw
    try:
        text, n = _pdf_text(data)
    except Exception:
        return Source(kind="deck", ref=url, text="", live_url=None, meta={"error": "deck_not_readable"})

    live_url = _first_live_link(text)
    return Source(kind="deck", ref=url, text=text, live_url=live_url, meta={"slides": n})


# ---------------------------------------------------------------------------
# normalize / one_box


def normalize(*, repo: str | None = None, page: str | None = None, deck: str | None = None,
              deck_bytes: bytes | None = None, pitch: str | None = None,
              fetcher: probes.Fetcher | None = None, resolver: probes.Resolver | None = None) -> dict:
    warnings: list[str] = []
    sources: list[Source] = []
    source_kinds: list[str] = []
    sections: list[str] = []

    repo_source: Source | None = None
    page_source: Source | None = None
    deck_source: Source | None = None

    if repo:
        repo_source = read_repo(repo, fetcher=fetcher, resolver=resolver)
        sources.append(repo_source)
        source_kinds.append("repo")
        if repo_source.meta.get("error"):
            warnings.append(f"repo: {repo_source.meta['error']}")
        sections.append(f"=== REPO {repo} ===\n{repo_source.text}")

    if page:
        page_source = read_page(page, fetcher=fetcher, resolver=resolver)
        sources.append(page_source)
        source_kinds.append("page")
        if page_source.meta.get("error"):
            warnings.append(f"page: {page_source.meta['error']}")
        sections.append(f"=== PAGE {page} ===\n{page_source.text}")

    if deck or deck_bytes is not None:
        deck_ref = deck_bytes if deck_bytes is not None else deck
        deck_source = read_deck(deck_ref, fetcher=fetcher, resolver=resolver)
        sources.append(deck_source)
        source_kinds.append("deck")
        if deck_source.meta.get("error"):
            warnings.append(f"deck: {deck_source.meta['error']}")
        sections.append(f"=== DECK {deck_source.ref} ===\n{deck_source.text}")

    if pitch:
        pitch_source = Source(kind="pitch", ref="pasted", text=pitch, live_url=None, meta={})
        sources.append(pitch_source)
        source_kinds.append("pitch")
        sections.append(f"=== PITCH ===\n{pitch}")

    live_url = None
    if page_source and page_source.live_url:
        live_url = page_source.live_url
    elif repo_source and repo_source.live_url:
        live_url = repo_source.live_url
    elif deck_source and deck_source.live_url:
        live_url = deck_source.live_url

    primary_kind = source_kinds[0] if source_kinds else "pitch"

    return {
        "text": "\n\n".join(sections),
        "live_url": live_url,
        "source_kinds": source_kinds,
        "sources": [s.as_dict() for s in sources],
        "primary_kind": primary_kind,
        "warnings": warnings,
    }


def one_box(s: str, *, fetcher: probes.Fetcher | None = None, resolver: probes.Resolver | None = None) -> dict:
    kind = detect(s)
    if kind == "repo":
        return normalize(repo=s, fetcher=fetcher, resolver=resolver)
    if kind == "page":
        return normalize(page=s, fetcher=fetcher, resolver=resolver)
    if kind == "deck":
        return normalize(deck=s, fetcher=fetcher, resolver=resolver)
    return normalize(pitch=s, fetcher=fetcher, resolver=resolver)
