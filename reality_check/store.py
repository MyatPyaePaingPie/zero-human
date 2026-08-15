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
CREATE TABLE IF NOT EXISTS payment_claims (
  session_id TEXT PRIMARY KEY, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS raters (
  phone TEXT PRIMARY KEY, opted_out INTEGER NOT NULL DEFAULT 0, joined_at TEXT NOT NULL, last_sent_at TEXT
);
CREATE TABLE IF NOT EXISTS text_threads (
  id INTEGER PRIMARY KEY AUTOINCREMENT, phone_hash TEXT NOT NULL, job_id TEXT NOT NULL,
  links_json TEXT NOT NULL, created_at TEXT NOT NULL
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


def patch_job_state(job_id: str, key: str, value) -> None:
    """Read-modify-write a single state key, atomically under the same lock put_job uses. A
    background writer (e.g. the probe thread in judge.py) that only owns one key must never
    clobber the rest of state with a stale wholesale write, and must never be clobbered by one
    either -- so this reads fresh from the DB at write time, not from whatever the caller last
    saw. No-op if the job no longer exists."""
    with _lock, conn() as c:
        row = c.execute("SELECT status, state FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            return
        state = json.loads(row["state"])
        state[key] = value
        c.execute("UPDATE jobs SET updated_at=?, state=? WHERE job_id=?", (now(), json.dumps(state), job_id))


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


def claim_payment(session_id: str) -> bool:
    """Atomic idempotency claim (INSERT OR IGNORE on the PK). True = this caller owns processing.
    Safe across the webhook and the poller, in-process or across processes."""
    with _lock, conn() as c:
        cur = c.execute("INSERT OR IGNORE INTO payment_claims(session_id, created_at) VALUES(?,?)", (session_id, now()))
        return cur.rowcount == 1


def release_payment_claim(session_id: str) -> None:
    with _lock, conn() as c:
        c.execute("DELETE FROM payment_claims WHERE session_id=?", (session_id,))


def rater_upsert(phone: str, *, opted_out: bool) -> bool:
    """True if newly enrolled."""
    with _lock, conn() as c:
        row = c.execute("SELECT 1 FROM raters WHERE phone=?", (phone,)).fetchone()
        if row:
            c.execute("UPDATE raters SET opted_out=? WHERE phone=?", (int(opted_out), phone))
            return False
        c.execute("INSERT INTO raters(phone,opted_out,joined_at) VALUES(?,?,?)", (phone, int(opted_out), now()))
        return True


def raters_pick(n: int) -> list[str]:
    with conn() as c:
        rows = c.execute("SELECT phone FROM raters WHERE opted_out=0 ORDER BY last_sent_at IS NOT NULL, last_sent_at ASC LIMIT ?", (n,)).fetchall()
    return [r["phone"] for r in rows]


def rater_touch(phone: str) -> None:
    with _lock, conn() as c:
        c.execute("UPDATE raters SET last_sent_at=? WHERE phone=?", (now(), phone))


def raters_count() -> int:
    with conn() as c:
        return int(c.execute("SELECT COUNT(*) n FROM raters WHERE opted_out=0").fetchone()["n"])


def human_answers(job_id: str) -> list[dict]:
    with conn() as c:
        rows = c.execute("SELECT source,respondent,claim_idx,answer_yes,free_text,created_at FROM human_answers WHERE job_id=? ORDER BY id", (job_id,)).fetchall()
    return [dict(r) for r in rows]


def ledger_add(job_id: str | None, kind: str, amount_usd: float, note: str = "") -> None:
    with _lock, conn() as c:
        c.execute("INSERT INTO ledger(job_id,kind,amount_usd,note,created_at) VALUES(?,?,?,?,?)", (job_id, kind, amount_usd, note, now()))


def ledger_add_once(job_id: str, kind: str, amount_usd: float, note: str = "") -> bool:
    """Write the row only if this job has no row of this kind yet (payment retries must not double-count)."""
    with _lock, conn() as c:
        if c.execute("SELECT 1 FROM ledger WHERE job_id=? AND kind=? LIMIT 1", (job_id, kind)).fetchone():
            return False
        c.execute("INSERT INTO ledger(job_id,kind,amount_usd,note,created_at) VALUES(?,?,?,?,?)", (job_id, kind, amount_usd, note, now()))
    return True


def ledger_totals() -> dict:
    with conn() as c:
        rows = c.execute("SELECT kind, SUM(amount_usd) s, COUNT(*) n FROM ledger GROUP BY kind").fetchall()
    t = {r["kind"]: {"usd": r["s"], "n": r["n"]} for r in rows}
    rev = t.get("revenue", {}).get("usd", 0.0)
    cost = sum(v["usd"] for k, v in t.items() if k.startswith("cost"))
    return {"by_kind": t, "revenue_usd": rev, "cost_usd": cost, "margin_usd": rev - cost}


def text_thread_put(phone_hash: str, job_id: str, links: dict) -> None:
    """One row per text-intake job for this phone (issue #23); `text_thread_last` reads the
    newest. Never upserts: RERUN needs the prior row's job_id/links still intact when the new
    row lands."""
    with _lock, conn() as c:
        c.execute("INSERT INTO text_threads(phone_hash,job_id,links_json,created_at) VALUES(?,?,?,?)",
                  (phone_hash, job_id, json.dumps(links), now()))


def text_thread_last(phone_hash: str) -> dict | None:
    with conn() as c:
        r = c.execute(
            "SELECT job_id, links_json, created_at FROM text_threads WHERE phone_hash=? ORDER BY id DESC LIMIT 1",
            (phone_hash,),
        ).fetchone()
    if not r:
        return None
    return {"job_id": r["job_id"], "links": json.loads(r["links_json"]), "created_at": r["created_at"]}


def event(job_id: str | None, kind: str, payload: dict | None = None) -> None:
    with _lock, conn() as c:
        c.execute("INSERT INTO events(job_id,kind,payload,created_at) VALUES(?,?,?,?)", (job_id, kind, json.dumps(payload or {}), now()))


def events(limit: int = 200) -> list[dict]:
    with conn() as c:
        rows = c.execute("SELECT job_id,kind,payload,created_at FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [{"job_id": r["job_id"], "kind": r["kind"], "payload": json.loads(r["payload"]), "at": r["created_at"]} for r in rows]
