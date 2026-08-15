"""SQLite store: jobs, human answers, money ledger. One row per decision (dedupe by job_id)."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

DB_PATH = Path(os.environ.get("RC_DB", "reality_check.db"))
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  job_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  buyer_id TEXT, status TEXT NOT NULL, request TEXT NOT NULL, state TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS human_answers (
  id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL, source TEXT NOT NULL,
  respondent TEXT, claim_idx INTEGER NOT NULL DEFAULT 0, answer_yes INTEGER, free_text TEXT, created_at TEXT NOT NULL,
  UNIQUE(job_id, source, respondent, claim_idx)
);
CREATE TABLE IF NOT EXISTS ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, kind TEXT NOT NULL,
  amount_usd REAL NOT NULL, note TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, kind TEXT NOT NULL, payload TEXT, created_at TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init() -> None:
    with conn() as c:
        c.executescript(SCHEMA)


def put_job(job_id: str, buyer_id: str, status: str, request: dict, state: dict) -> None:
    with _lock, conn() as c:
        c.execute(
            "INSERT INTO jobs(job_id,created_at,updated_at,buyer_id,status,request,state) VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(job_id) DO UPDATE SET updated_at=excluded.updated_at,status=excluded.status,state=excluded.state",
            (job_id, now(), now(), buyer_id, status, json.dumps(request), json.dumps(state)),
        )


def get_job(job_id: str) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
    if not r:
        return None
    return {"job_id": r["job_id"], "status": r["status"], "buyer_id": r["buyer_id"], "created_at": r["created_at"],
            "request": json.loads(r["request"]), "state": json.loads(r["state"])}


def list_jobs(limit: int = 50) -> list[dict]:
    with conn() as c:
        rows = c.execute("SELECT job_id FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [j for j in (get_job(r["job_id"]) for r in rows) if j]


def add_human_answer(job_id: str, source: str, respondent: str, answer_yes: bool | None, free_text: str, claim_idx: int = 0) -> bool:
    with _lock, conn() as c:
        try:
            c.execute("INSERT INTO human_answers(job_id,source,respondent,claim_idx,answer_yes,free_text,created_at) VALUES(?,?,?,?,?,?,?)",
                      (job_id, source, respondent, claim_idx, None if answer_yes is None else int(answer_yes), free_text[:2000], now()))
            return True
        except sqlite3.IntegrityError:
            return False


def human_answers(job_id: str) -> list[dict]:
    with conn() as c:
        rows = c.execute("SELECT source,respondent,claim_idx,answer_yes,free_text,created_at FROM human_answers WHERE job_id=? ORDER BY id", (job_id,)).fetchall()
    return [dict(r) for r in rows]


def ledger_add(job_id: str | None, kind: str, amount_usd: float, note: str = "") -> None:
    with _lock, conn() as c:
        c.execute("INSERT INTO ledger(job_id,kind,amount_usd,note,created_at) VALUES(?,?,?,?,?)", (job_id, kind, amount_usd, note, now()))


def ledger_totals() -> dict:
    with conn() as c:
        rows = c.execute("SELECT kind, SUM(amount_usd) s, COUNT(*) n FROM ledger GROUP BY kind").fetchall()
    t = {r["kind"]: {"usd": r["s"], "n": r["n"]} for r in rows}
    rev = t.get("revenue", {}).get("usd", 0.0)
    cost = sum(v["usd"] for k, v in t.items() if k.startswith("cost"))
    return {"by_kind": t, "revenue_usd": rev, "cost_usd": cost, "margin_usd": rev - cost}


def event(job_id: str | None, kind: str, payload: dict | None = None) -> None:
    with _lock, conn() as c:
        c.execute("INSERT INTO events(job_id,kind,payload,created_at) VALUES(?,?,?,?)", (job_id, kind, json.dumps(payload or {}), now()))


def events(limit: int = 200) -> list[dict]:
    with conn() as c:
        rows = c.execute("SELECT job_id,kind,payload,created_at FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [{"job_id": r["job_id"], "kind": r["kind"], "payload": json.loads(r["payload"]), "at": r["created_at"]} for r in rows]
