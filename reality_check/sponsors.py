"""Sponsor depth detection: mechanical, zero model calls.

`docs/sponsor-signatures.md` carries one fenced json block per sponsor (code/text patterns,
capabilities with signals, meaningful_use, fake_tells, cheapest_honest_add) plus a `_depth_ladder`.
This module greps the bundle text (README + manifests + repo file tree + module docstrings + page
text + deck text, assembled in `reality_check.sources`) and reports, per sponsor, WHICH
capabilities are evidenced, not merely whether the name appears.

Depth ladder (0-4): 0 nothing, 1 name-dropped (text only), 2 wired (code hits, no call site),
3 used (>= 1 capability), 4 deep (>= half the capabilities). Capability hits are only counted when
the sponsor has at least one `code` hit: capability signals are short by design ("fix", "bug",
"before"), and without that gate a README full of ordinary English would score depth 3 for a
sponsor that is not in the repo at all.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SIGNATURES = REPO_ROOT / "docs" / "sponsor-signatures.md"

DEPTH_WORDS = {0: "not used", 1: "name-dropped", 2: "wired", 3: "used", 4: "deep"}

_JSON_BLOCK_RE = re.compile(r"```json\s*\n(.*?)\n```", re.S)
# "reality_check/terac_client.py: Terac REST v2 client" or a bare file-tree path line
_PATH_RE = re.compile(r"[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)*\.[A-Za-z0-9]{1,6}")


@lru_cache(maxsize=8)
def _load(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise ValueError(f"sponsor signatures not found: {path}")
    blocks = _JSON_BLOCK_RE.findall(p.read_text(encoding="utf-8"))
    if not blocks:
        raise ValueError(f"no fenced ```json block in {path}")
    merged: dict = {}
    for i, block in enumerate(blocks):
        try:
            data = json.loads(block)
        except json.JSONDecodeError as exc:
            raise ValueError(f"sponsor signature block {i} in {path} does not parse: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"sponsor signature block {i} in {path} is not an object")
        merged.update(data)
    if not merged:
        raise ValueError(f"no sponsor signatures in {path}")
    merged.setdefault("_depth_ladder", dict(DEPTH_WORDS))
    return merged


def load_signatures(path: str | None = None) -> dict:
    """Parse (and cache) every fenced json block in the signatures doc, merged by sponsor id.

    Prose between the blocks is ignored. `_depth_ladder` rides along under its own key.
    """
    return _load(str(Path(path) if path else DEFAULT_SIGNATURES))


# --------------------------------------------------------------------------- detection

def _lines(text: str) -> list[tuple[str, str]]:
    """(original line, lowercased line) for every line of the bundle."""
    return [(ln, ln.lower()) for ln in (text or "").splitlines()]


def _file_of(line: str) -> str:
    """The file path a matched line sits on, when the line is a file-tree entry or a
    'path: docstring' line. Otherwise 'text'."""
    head = line.strip()
    m = re.match(r"^[-*\s]*([A-Za-z0-9_.\-/]+\.[A-Za-z0-9]{1,6})\s*(?::|$)", head)
    if m:
        return m.group(1)
    m = _PATH_RE.search(head)
    if m and "/" in m.group(0):
        return m.group(0)
    return "text"


def _find(pattern: str, lines: list[tuple[str, str]]) -> tuple[str, str] | None:
    """First (line, file) where `pattern` appears, case-insensitively."""
    pat = str(pattern).lower().strip()
    if not pat:
        return None
    for original, low in lines:
        if pat in low:
            return original.strip()[:200], _file_of(original)
    return None


def _hits(patterns, lines: list[tuple[str, str]]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for pat in patterns or []:
        found = _find(pat, lines)
        if found:
            out.append((str(pat), found[0]))
    return out


def detect_one(text: str, spec: dict) -> dict:
    """Detect one sponsor's depth of use in the bundle text. Zero model calls."""
    lines = _lines(text)
    code_hits = _hits(spec.get("code"), lines)
    text_hits = _hits(spec.get("text"), lines)
    caps_spec = list(spec.get("capabilities") or [])

    capabilities: list[dict] = []
    for cap in caps_spec:
        evidence = ""
        if code_hits:  # a capability needs the sponsor to be in the code at all
            for signal in cap.get("signals") or []:
                found = _find(signal, lines)
                if found:
                    evidence = f"{signal} in {found[1]}"
                    break
        capabilities.append({
            "id": cap.get("id"), "what": cap.get("what"),
            "hit": bool(evidence), "evidence": evidence,
        })

    n_hit = sum(1 for c in capabilities if c["hit"])
    if not code_hits and not text_hits:
        depth = 0
    elif not code_hits:
        depth = 1
    elif n_hit == 0:
        depth = 2
    elif caps_spec and n_hit * 2 >= len(caps_spec):
        depth = 4
    else:
        depth = 3

    unticked = [c for c in capabilities if not c["hit"]]
    next_cap = ({"id": unticked[0]["id"], "what": unticked[0]["what"]} if unticked else None)
    fired = [t for t in (spec.get("fake_tells") or []) if _find(t, lines)]
    return {
        "code_hits": code_hits,
        "text_hits": text_hits,
        "capabilities": capabilities,
        "depth": depth,
        "depth_word": DEPTH_WORDS[depth],
        "next_capability": next_cap,
        "cheapest_honest_add": str(spec.get("cheapest_honest_add") or ""),
        "fake_tells_fired": fired,
        "meaningful_use": list(spec.get("meaningful_use") or []),
        "required": bool(spec.get("required")),
        "use_line": use_line(capabilities, next_cap),
    }


def detect(text: str, sig: dict) -> dict:
    """Per sponsor id, the detection dict from `detect_one`. `_depth_ladder` is passed through."""
    out: dict = {}
    for sponsor_id, spec in (sig or {}).items():
        if sponsor_id.startswith("_") or not isinstance(spec, dict):
            out[sponsor_id] = spec
            continue
        out[sponsor_id] = detect_one(text, spec)
    return out


def use_line(capabilities: list[dict], next_cap: dict | None) -> str:
    """"used k of n: a, b, c. Next: d" - the one line a judge reads."""
    used = [str(c["id"]) for c in capabilities if c["hit"]]
    line = f"used {len(used)} of {len(capabilities)}"
    if used:
        line += ": " + ", ".join(used)
    line += "."
    if next_cap:
        line += f" Next: {next_cap['id']}"
    return line


def hit_strings(det: dict) -> list[str]:
    """The matched patterns (code first, then text) - what `sponsor_evidence` returns."""
    return [p for p, _ in det.get("code_hits", [])] + [p for p, _ in det.get("text_hits", [])]
