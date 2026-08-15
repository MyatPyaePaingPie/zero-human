"""Human evidence sources. One interface, several backends.

launch(job_id, question, input_text, n) -> panel handle. Humans answer through OUR rating page
(/rate/{job_id}?src=<source>&r=<respondent>) whatever the recruiting channel: Terac activity
task_url points here (Terac appends teracSubmissionId), Linq texts a link here, in-room QR
points here. Answers land in store.human_answers and settlement re-aggregates.

`terac` and `linq` backends are owned by the money-swarm session (terac_client.py,
linq_client.py); this module only defines the contract and the local backend.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

PUBLIC_BASE = os.environ.get("RC_PUBLIC_BASE", "http://localhost:8000")


@dataclass(frozen=True)
class PanelHandle:
    source: str
    external_id: str | None
    rate_url: str
    n_requested: int
    price_usd: float


class Panel(Protocol):
    name: str

    def launch(self, job_id: str, question: str, input_text: str, n: int, approve=None) -> PanelHandle: ...


class LocalPanel:
    """No recruiting: hands back the rating URL. Used for in-room QR / dev."""
    name = "local"

    def launch(self, job_id: str, question: str, input_text: str, n: int, approve=None) -> PanelHandle:
        return PanelHandle("local", None, f"{PUBLIC_BASE}/rate/{job_id}?src=local", n, 0.0)


REGISTRY: dict[str, Panel] = {"local": LocalPanel()}


def register(panel: Panel) -> None:
    REGISTRY[panel.name] = panel


def for_arm(arm: str) -> Panel:
    """Map a VOI arm to a recruiting backend; fall back to local when the backend is not wired."""
    key = {"linq_panel": "linq", "terac_general": "terac", "terac_expert": "terac"}.get(arm, "local")
    return REGISTRY.get(key, REGISTRY["local"])
