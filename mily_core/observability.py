"""Structured JSON logging helpers for MILY.

Only explicit event metadata is emitted. Sensitive field names and common
credential patterns are redacted before serialization; callers should still
avoid passing secrets or private user content to logs.
"""

from __future__ import annotations

import json
import logging
import math
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

_SENSITIVE_KEY = re.compile(
    r"(?:secret|password|passwd|token|api[_-]?key|authorization|credential|cookie)",
    re.IGNORECASE,
)
_SECRET_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(
        r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|password)"
        r"(\s*[:=]\s*)([^\s,;]+)"
    ),
)
_MAX_TEXT = 500
_MAX_DEPTH = 5
_MAX_ITEMS = 50


def _redact_text(value: str) -> str:
    result = value[:_MAX_TEXT]
    result = _SECRET_PATTERNS[0].sub("Bearer [REDACTED]", result)
    result = _SECRET_PATTERNS[1].sub("[REDACTED_KEY]", result)
    result = _SECRET_PATTERNS[2].sub(r"\1\2[REDACTED]", result)
    return result


def _safe_value(value: Any, *, depth: int = 0) -> Any:
    """Convert values to bounded JSON-safe data and redact sensitive fields."""
    if depth >= _MAX_DEPTH:
        return "[MAX_DEPTH]"
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, Mapping):
        safe: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= _MAX_ITEMS:
                safe["_truncated"] = True
                break
            safe_key = _redact_text(str(key)[:100])
            safe[safe_key] = (
                "[REDACTED]" if _SENSITIVE_KEY.search(safe_key)
                else _safe_value(item, depth=depth + 1)
            )
        return safe
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        safe_items = [_safe_value(item, depth=depth + 1) for item in items[:_MAX_ITEMS]]
        if len(items) > _MAX_ITEMS:
            safe_items.append("[TRUNCATED]")
        return safe_items
    return _redact_text(str(value))


class StructuredLogger:
    """Emit one compact JSON object per event through Python's logging system."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("mily")

    def emit(
        self,
        event: str,
        *,
        task_id: str | None = None,
        status: str | None = None,
        duration_ms: float | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        if not isinstance(event, str) or not event.strip():
            raise ValueError("event must be a non-empty string")
        if task_id is not None and (not isinstance(task_id, str) or not task_id.strip()):
            raise ValueError("task_id must be a non-empty string or None")
        if status is not None and not isinstance(status, str):
            raise ValueError("status must be a string or None")
        if duration_ms is not None and (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, (int, float))
            or not math.isfinite(duration_ms)
            or duration_ms < 0
        ):
            raise ValueError("duration_ms must be a finite non-negative number or None")
        if details is not None and not isinstance(details, Mapping):
            raise TypeError("details must be a mapping or None")

        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": _redact_text(event.strip()),
            "task_id": _redact_text(task_id.strip()) if task_id else None,
            "status": _redact_text(status.strip()) if status else None,
            "duration_ms": duration_ms,
            "details": _safe_value(details or {}),
        }
        self._logger.info(
            json.dumps(record, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        )
