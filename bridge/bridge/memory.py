"""SQLite + FTS5 backed cross-thread memory recall for the bridge demo."""
from __future__ import annotations

import datetime
import logging
import sqlite3
from pathlib import Path

from .config import BridgeConfig

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT NOT NULL, thread_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user','assistant')),
    content TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(content, content='messages', content_rowid='id');
"""

PREFIX = "Here are the dialogs found in db, you just ignore if they are irrelevant:"


class Memory:
    def __init__(self, config: BridgeConfig, data_dir: str | Path):
        self.config = config
        self.db_path = Path(data_dir) / "memory.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
        except Exception:
            logger.exception("memory: failed to initialize sqlite db at %s", self.db_path)
            self._conn = None

    def record(self, channel_id: str, thread_id: str, role: str, content: str) -> None:
        if self._conn is None:
            return
        try:
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            cur = self._conn.execute(
                "INSERT INTO messages (channel_id, thread_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (channel_id, thread_id, role, content, now),
            )
            rowid = cur.lastrowid
            self._conn.execute(
                "INSERT INTO messages_fts (rowid, content) VALUES (?, ?)",
                (rowid, content),
            )
            self._conn.commit()
        except Exception:
            logger.exception("memory: failed to record message")

    def inject_context(self, channel_id: str, thread_id: str, message_text: str) -> str:
        cfg = self.config.memory
        if not cfg.enabled:
            return message_text
        if len(message_text) < cfg.context_min_chars:
            return message_text
        if self._conn is None:
            return message_text
        try:
            phrase = message_text.replace('"', '""')
            rows = self._conn.execute(
                """
                SELECT m.role, m.content, bm25(messages_fts) AS rank
                FROM messages_fts
                JOIN messages m ON m.id = messages_fts.rowid
                WHERE messages_fts MATCH ?
                  AND m.channel_id = ?
                  AND m.thread_id != ?
                ORDER BY rank ASC
                LIMIT ?
                """,
                (f'"{phrase}"', channel_id, thread_id, cfg.context_max_results),
            ).fetchall()
        except Exception:
            logger.exception("memory: failed to query context")
            return message_text

        if not rows:
            return message_text

        lines = [f"[{role}] {content}" for role, content, _rank in rows]

        try:
            budget = cfg.context_max_chars
            body = "\n".join(lines)
            block = f"{PREFIX}\n```\n{body}\n```\n\n{message_text}"
            while len(block) > budget and lines:
                lines.pop()
                body = "\n".join(lines)
                if not lines:
                    return message_text
                block = f"{PREFIX}\n```\n{body}\n```\n\n{message_text}"
            return block
        except Exception:
            logger.exception("memory: failed to build context block")
            return message_text

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
