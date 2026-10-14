"""Bounded, in-process memory primitives for MILY.

This module is intentionally non-persistent: entries disappear when the process
ends. Callers should avoid placing secrets or sensitive personal data here.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class MemoryType(str, Enum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    REFLECTIVE = "reflective"


class MemorySource(str, Enum):
    USER = "user"
    SELF = "self"
    TOOL = "tool"
    EXTERNAL = "external"


@dataclass
class MemoryEntry:
    """One memory item with provenance and lightweight retrieval metadata."""

    content: str
    memory_type: MemoryType = MemoryType.EPISODIC
    source: MemorySource = MemorySource.USER
    importance: float = 0.5
    confidence: float = 0.5
    entry_id: str = field(default_factory=lambda: uuid4().hex)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    access_count: int = 0
    last_accessed: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.content, str) or not self.content.strip():
            raise ValueError("Memory content must be a non-empty string")
        if not isinstance(self.memory_type, MemoryType):
            raise ValueError("memory_type must be a MemoryType")
        if not isinstance(self.source, MemorySource):
            raise ValueError("source must be a MemorySource")
        for name in ("importance", "confidence"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a number between 0 and 1")
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")


class MemoryStore:
    """A bounded in-memory store; it does not persist or execute external tools."""

    def __init__(self, max_entries: int = 500) -> None:
        if isinstance(max_entries, bool) or not isinstance(max_entries, int) or max_entries < 1:
            raise ValueError("max_entries must be a positive integer")
        self.max_entries = max_entries
        self._entries: dict[str, MemoryEntry] = {}

    def add(self, entry: MemoryEntry) -> MemoryEntry:
        if not isinstance(entry, MemoryEntry):
            raise TypeError("entry must be a MemoryEntry")
        if entry.entry_id in self._entries:
            raise ValueError("entry_id already exists")
        self._entries[entry.entry_id] = entry
        while len(self._entries) > self.max_entries:
            oldest_id = next(iter(self._entries))
            del self._entries[oldest_id]
        return entry

    def get(self, entry_id: str) -> MemoryEntry | None:
        entry = self._entries.get(entry_id)
        if entry is not None:
            entry.access_count += 1
            entry.last_accessed = datetime.now(timezone.utc).isoformat()
        return entry

    def search(
        self, query: str = "", memory_type: MemoryType | None = None, limit: int = 20
    ) -> list[MemoryEntry]:
        if not isinstance(query, str):
            raise TypeError("query must be a string")
        if memory_type is not None and not isinstance(memory_type, MemoryType):
            raise ValueError("memory_type must be a MemoryType or None")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        needle = query.casefold().strip()
        matches = [
            entry for entry in self._entries.values()
            if (not needle or needle in entry.content.casefold())
            and (memory_type is None or entry.memory_type == memory_type)
        ]
        matches.sort(key=lambda item: (item.importance, item.created_at), reverse=True)
        return matches[:limit]

    def delete(self, entry_id: str) -> bool:
        return self._entries.pop(entry_id, None) is not None

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)
