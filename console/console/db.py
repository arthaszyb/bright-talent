"""SQLite storage for the console's own state: drafts, audit_events, skill_snapshots.

Table shapes follow docs/60-console/design.md §"Database Schema" (SQLite substituted
for MySQL/InnoDB per the doc's own demo note: JSON columns as TEXT, secondary indexes
as CREATE INDEX). Table names are the doc's simplified (non-prefixed) names.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS drafts (
    draft_id TEXT PRIMARY KEY,
    instance_id TEXT NOT NULL,
    state TEXT NOT NULL,
    operation_type TEXT NOT NULL,
    target_branch TEXT,
    base_commit TEXT,
    mr_iid INTEGER,
    mr_url TEXT,
    payload TEXT,
    files TEXT,
    created_by_email TEXT,
    created_by_name TEXT,
    updated_by_email TEXT,
    updated_by_name TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_drafts_instance_state ON drafts (instance_id, state);
CREATE INDEX IF NOT EXISTS idx_drafts_updated_at ON drafts (updated_at);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    instance_id TEXT,
    draft_id TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    actor_email TEXT,
    actor_name TEXT,
    actor_id TEXT,
    from_state TEXT,
    to_state TEXT,
    request_id TEXT,
    route TEXT,
    method TEXT,
    permission_source TEXT,
    error TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_instance_created ON audit_events (instance_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_draft ON audit_events (draft_id);
CREATE INDEX IF NOT EXISTS idx_audit_actor_created ON audit_events (actor_email, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_action_created ON audit_events (action, created_at);

CREATE TABLE IF NOT EXISTS skill_snapshots (
    instance_id TEXT PRIMARY KEY,
    payload TEXT,
    payload_hash TEXT,
    sync_status TEXT,
    stale INTEGER DEFAULT 0,
    last_error TEXT,
    source_repo_head TEXT,
    runtime_lock_hash TEXT,
    synced_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_skill_snapshots_status ON skill_snapshots (sync_status, stale);
CREATE INDEX IF NOT EXISTS idx_skill_snapshots_synced ON skill_snapshots (synced_at);
"""


class Database:
    """Thin synchronous SQLite wrapper. One connection per process, guarded by a lock
    (uvicorn's default single-worker dev server + FastAPI's threaded route handling
    means we can get concurrent callers even without async DB access)."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            self._conn.commit()
            return cur

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            return cur.fetchall()

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def dumps(obj: Any) -> str:
    return json.dumps(obj, default=str)


def loads(text: str | None, default: Any = None) -> Any:
    if not text:
        return default
    return json.loads(text)


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}
