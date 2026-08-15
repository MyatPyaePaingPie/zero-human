"""Agent-ready scan (issue #7): a single POST to isitagentready.com/api/scan, folded into
probes.py findings with prefix `agentready/<category>-failing`. Fails closed: any error
(network, timeout, bad JSON, non-2xx) returns (None, []) and never blocks the rest of a run.
"""
from __future__ import annotations

from typing import Any, Callable

import httpx

API_URL = "https://isitagentready.com/api/scan"
TIMEOUT_S = 10.0
CATEGORIES = ("discoverability", "contentAccessibility", "botAccessControl", "protocolDiscovery", "commerce")
# the live API names the protocol category "discovery"; the lens claim id says protocolDiscovery
_ALIAS = {"discovery": "protocolDiscovery"}

Poster = Callable[[str, float], Any]


def _default_post(url: str, timeout_s: float) -> Any:
    r = httpx.post(API_URL, json={"url": url}, timeout=timeout_s)
    r.raise_for_status()
    return r.json()


def _category_name(item: Any) -> str | None:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return item.get("category") or item.get("id") or item.get("name")
    return None


def scan(url: str, *, poster: Poster | None = None, timeout_s: float = TIMEOUT_S) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    poster = poster or _default_post
    try:
        data = poster(url, timeout_s)
    except Exception:
        return None, []
    if not isinstance(data, dict):
        return None, []

    checks = data.get("checks") if isinstance(data.get("checks"), dict) else {}
    failing: list[dict[str, Any]] = []
    passing: list[str] = []
    for cat, sub in checks.items():
        cat = _ALIAS.get(cat, cat)
        if not isinstance(sub, dict):
            continue
        bad = [(k, v) for k, v in sub.items() if isinstance(v, dict) and str(v.get("status", "")).lower() in ("fail", "failed", "error")]
        good = [k for k, v in sub.items() if isinstance(v, dict) and str(v.get("status", "")).lower() in ("pass", "ok", "passed")]
        passing.extend(f"{cat}.{k}" for k in good)
        if bad:
            failing.append({"category": cat, "checks": [f"{k}: {v.get('message', '')}"[:120] for k, v in bad]})
    # older/alternate shape: explicit failing/passing lists
    for item in data.get("failing") or []:
        cat = _category_name(item)
        if cat and not any(f["category"] == cat for f in failing):
            failing.append({"category": cat, "checks": [str(item)[:120]]})
    passing.extend(x for x in (data.get("passing") or []) if isinstance(x, str))
    result = {
        "level": data.get("level"),
        "levelName": data.get("levelName"),
        "failing": failing,
        "passing": passing,
        "summary": data.get("summary"),
    }

    findings: list[dict[str, Any]] = []
    for item in result["failing"]:
        cat = item["category"]
        if cat in CATEGORIES:
            findings.append({
                "id": f"agentready/{cat}-failing", "severity": "warning", "page": None,
                "message": f"isitagentready: {cat} is failing ({len(item['checks'])} checks).",
                "fix": "See isitagentready.com for the exact file or header to add.",
                "evidence": "; ".join(item["checks"])[:200],
            })
    return result, findings
