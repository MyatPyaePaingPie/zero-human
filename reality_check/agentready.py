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

    result = {
        "level": data.get("level"),
        "levelName": data.get("levelName"),
        "failing": data.get("failing") or [],
        "passing": data.get("passing") or [],
        "summary": data.get("summary"),
    }

    findings: list[dict[str, Any]] = []
    for item in result["failing"]:
        cat = _category_name(item)
        if cat in CATEGORIES:
            findings.append({
                "id": f"agentready/{cat}-failing", "severity": "warning", "page": None,
                "message": f"isitagentready: {cat} is failing.", "fix": None,
                "evidence": str(item)[:200],
            })
    return result, findings
