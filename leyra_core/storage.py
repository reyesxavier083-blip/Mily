"""Persistent storage for LEYRA (SQLite, stdlib only).

Tables hold conversations, messages, memories, settings and the app-integration
audit trail. Data stays on the machine running the API; nothing is uploaded.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time
import uuid
from typing import Any, Iterable

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    pinned INTEGER NOT NULL DEFAULT 0,
    project TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    meta TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, created_at);
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    normalized TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'general',
    provenance TEXT NOT NULL DEFAULT 'user',
    confidence REAL NOT NULL DEFAULT 0.7,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(normalized)
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS integration_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    package_name TEXT NOT NULL,
    event TEXT NOT NULL,
    detail TEXT NOT NULL,
    at REAL NOT NULL
);
"""


def _normalize(text: str) -> str:
    return " ".join(str(text).lower().split())[:2000]


def _digest(text: str) -> str:
    return hashlib.sha256(_normalize(text).encode("utf-8")).hexdigest()


class Store:
    """Small SQLite wrapper with explicit, bounded queries."""

    def __init__(self, path: str | Path = "leyra.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # -- conversations -----------------------------------------------------
    def list_conversations(self, *, limit: int = 50, query: str = "") -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        with self._lock:
            if query.strip():
                needle = f"%{query.strip()}%"
                rows = self._db.execute(
                    "SELECT c.*, (SELECT content FROM messages m WHERE m.conversation_id = c.id "
                    "ORDER BY m.created_at DESC LIMIT 1) AS last_message FROM conversations c "
                    "WHERE c.title LIKE ? OR EXISTS (SELECT 1 FROM messages m WHERE m.conversation_id = c.id "
                    "AND m.content LIKE ?) ORDER BY c.pinned DESC, c.updated_at DESC LIMIT ?",
                    (needle, needle, limit),
                ).fetchall()
            else:
                rows = self._db.execute(
                    "SELECT c.*, (SELECT content FROM messages m WHERE m.conversation_id = c.id "
                    "ORDER BY m.created_at DESC LIMIT 1) AS last_message FROM conversations c "
                    "ORDER BY c.pinned DESC, c.updated_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._conversation(row) for row in rows]

    def create_conversation(self, title: str = "Nueva conversación", project: str | None = None) -> dict[str, Any]:
        now = time.time()
        identifier = uuid.uuid4().hex
        clean_title = (title or "Nueva conversación").strip()[:120] or "Nueva conversación"
        with self._lock:
            self._db.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at, pinned, project) VALUES (?,?,?,?,0,?)",
                (identifier, clean_title, now, now, (project or None)),
            )
            self._db.commit()
        return {"id": identifier, "title": clean_title, "createdAt": now, "updatedAt": now,
                "pinned": False, "project": project}

    def get_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
            if row is None:
                return None
            messages = self._db.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC LIMIT 500",
                (conversation_id,),
            ).fetchall()
        data = self._conversation(row)
        data["messages"] = [self._message(message) for message in messages]
        return data

    def delete_conversation(self, conversation_id: str) -> bool:
        with self._lock:
            cursor = self._db.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
            self._db.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            self._db.commit()
        return cursor.rowcount > 0

    def rename_conversation(self, conversation_id: str, title: str) -> bool:
        clean = (title or "").strip()[:120]
        if not clean:
            return False
        with self._lock:
            cursor = self._db.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (clean, time.time(), conversation_id),
            )
            self._db.commit()
        return cursor.rowcount > 0

    def set_pinned(self, conversation_id: str, pinned: bool) -> bool:
        with self._lock:
            cursor = self._db.execute(
                "UPDATE conversations SET pinned = ?, updated_at = ? WHERE id = ?",
                (1 if pinned else 0, time.time(), conversation_id),
            )
            self._db.commit()
        return cursor.rowcount > 0

    def add_message(self, conversation_id: str, role: str, content: str,
                    meta: dict[str, Any] | None = None) -> dict[str, Any]:
        if role not in {"user", "assistant", "system", "tool"}:
            raise ValueError("Invalid message role")
        now = time.time()
        identifier = uuid.uuid4().hex
        text = str(content)[:120000]
        payload = json.dumps(meta or {}, ensure_ascii=False)[:20000]
        with self._lock:
            self._db.execute(
                "INSERT INTO messages (id, conversation_id, role, content, meta, created_at) VALUES (?,?,?,?,?,?)",
                (identifier, conversation_id, role, text, payload, now),
            )
            self._db.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id))
            self._db.commit()
        return {"id": identifier, "role": role, "content": text, "meta": meta or {}, "createdAt": now}

    def update_message(self, message_id: str, content: str, meta: dict[str, Any] | None = None) -> bool:
        with self._lock:
            if meta is None:
                cursor = self._db.execute("UPDATE messages SET content = ? WHERE id = ?", (str(content)[:120000], message_id))
            else:
                cursor = self._db.execute(
                    "UPDATE messages SET content = ?, meta = ? WHERE id = ?",
                    (str(content)[:120000], json.dumps(meta, ensure_ascii=False)[:20000], message_id),
                )
            self._db.commit()
        return cursor.rowcount > 0

    def delete_conversation_messages(self, conversation_id: str, after: float) -> int:
        with self._lock:
            cursor = self._db.execute(
                "DELETE FROM messages WHERE conversation_id = ? AND created_at >= ?",
                (conversation_id, after),
            )
            self._db.commit()
        return cursor.rowcount

    # -- memory ------------------------------------------------------------
    def list_memories(self, *, limit: int = 100, query: str = "") -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        with self._lock:
            if query.strip():
                rows = self._db.execute(
                    "SELECT * FROM memories WHERE normalized LIKE ? ORDER BY updated_at DESC LIMIT ?",
                    (f"%{_normalize(query)}%", limit),
                ).fetchall()
            else:
                rows = self._db.execute("SELECT * FROM memories ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._memory(row) for row in rows]

    def upsert_memory(self, text: str, *, category: str = "general", provenance: str = "user",
                      confidence: float = 0.7, memory_id: str | None = None) -> dict[str, Any]:
        clean = str(text).strip()[:4000]
        if not clean.strip():
            raise ValueError("Memory text is required")
        normalized = _digest(clean)
        now = time.time()
        with self._lock:
            existing = self._db.execute("SELECT * FROM memories WHERE normalized = ?", (normalized,)).fetchone()
            if existing is not None:
                self._db.execute(
                    "UPDATE memories SET updated_at = ?, confidence = MAX(confidence, ?), category = ? WHERE id = ?",
                    (now, float(confidence), str(category)[:60], existing["id"]),
                )
                self._db.commit()
                row = self._db.execute("SELECT * FROM memories WHERE id = ?", (existing["id"],)).fetchone()
                return self._memory(row)
            identifier = memory_id or uuid.uuid4().hex
            self._db.execute(
                "INSERT INTO memories (id, text, normalized, category, provenance, confidence, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (identifier, clean, normalized, str(category)[:60], str(provenance)[:60],
                 max(0.0, min(float(confidence), 1.0)), now, now),
            )
            self._db.commit()
            row = self._db.execute("SELECT * FROM memories WHERE id = ?", (identifier,)).fetchone()
        return self._memory(row)

    def delete_memory(self, memory_id: str) -> bool:
        with self._lock:
            cursor = self._db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            self._db.commit()
        return cursor.rowcount > 0

    def export_memories(self) -> list[dict[str, Any]]:
        return self.list_memories(limit=500)

    # -- settings ----------------------------------------------------------
    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except ValueError:
            return default

    def set_setting(self, key: str, value: Any) -> Any:
        payload = json.dumps(value, ensure_ascii=False)[:40000]
        with self._lock:
            self._db.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                (str(key)[:80], payload, time.time()),
            )
            self._db.commit()
        return value

    # -- integration audit -------------------------------------------------
    def log_integration(self, package_name: str, event: str, detail: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO integration_log (package_name, event, detail, at) VALUES (?,?,?,?)",
                (str(package_name)[:120], str(event)[:40], str(detail)[:240], time.time()),
            )
            self._db.commit()

    def integration_history(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM integration_log ORDER BY id DESC LIMIT ?", (max(1, min(int(limit), 200)),)
            ).fetchall()
        return [{"packageName": row["package_name"], "event": row["event"], "detail": row["detail"], "at": row["at"]}
                for row in rows]

    # -- stats -------------------------------------------------------------
    def stats(self) -> dict[str, Any]:
        with self._lock:
            conversations = self._db.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            messages = self._db.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            memories = self._db.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        return {"conversations": conversations, "messages": messages, "memories": memories,
                "path": str(self.path), "sizeBytes": self.path.stat().st_size if self.path.exists() else 0}

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _conversation(row: sqlite3.Row) -> dict[str, Any]:
        data = {
            "id": row["id"], "title": row["title"], "createdAt": row["created_at"],
            "updatedAt": row["updated_at"], "pinned": bool(row["pinned"]), "project": row["project"],
        }
        if "last_message" in row.keys():
            data["lastMessage"] = (row["last_message"] or "")[:160]
        return data

    @staticmethod
    def _message(row: sqlite3.Row) -> dict[str, Any]:
        try:
            meta = json.loads(row["meta"])
        except ValueError:
            meta = {}
        return {"id": row["id"], "role": row["role"], "content": row["content"],
                "meta": meta, "createdAt": row["created_at"]}

    @staticmethod
    def _memory(row: sqlite3.Row) -> dict[str, Any]:
        return {"id": row["id"], "text": row["text"], "category": row["category"],
                "provenance": row["provenance"], "confidence": row["confidence"],
                "createdAt": row["created_at"], "updatedAt": row["updated_at"]}


def iter_conversations(rows: Iterable[sqlite3.Row]) -> Iterable[dict[str, Any]]:  # pragma: no cover - helper
    for row in rows:
        yield Store._conversation(row)
