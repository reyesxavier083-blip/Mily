"""Task lifecycle coordinator for MILY.

This module coordinates state transitions, event notifications, and structured
logs. It deliberately does not execute tools or grant permissions.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from threading import RLock
from time import monotonic
from typing import Any

from mily_core.event_bus import EventBus
from mily_core.observability import StructuredLogger
from mily_core.tasks import TaskRecord, TaskStatus, transition_task


class TaskManager:
    """Manage task records and publish task lifecycle events safely."""

    def __init__(
        self,
        *,
        event_bus: EventBus | None = None,
        logger: StructuredLogger | None = None,
    ) -> None:
        self._lock = RLock()
        self._tasks: dict[str, TaskRecord] = {}
        self._started_at: dict[str, float] = {}
        self._event_bus = event_bus or EventBus()
        self._logger = logger or StructuredLogger()

    def create(self, task_id: str, *, metadata: dict[str, Any] | None = None) -> TaskRecord:
        """Create a pending task. Task IDs must be unique within this manager."""
        if metadata is not None and not isinstance(metadata, dict):
            raise TypeError("metadata must be a dictionary or None")
        record = TaskRecord(task_id=task_id, metadata=deepcopy(metadata or {}))
        with self._lock:
            if task_id in self._tasks:
                raise ValueError("task_id already exists")
            self._tasks[task_id] = record
            snapshot = self._snapshot(record)
        self._notify(snapshot, "task.created")
        return snapshot

    def start(self, task_id: str) -> TaskRecord:
        """Move a pending task into the running state."""
        with self._lock:
            record = self._require(task_id)
            transition_task(record, TaskStatus.RUNNING)
            self._started_at[task_id] = monotonic()
            snapshot = self._snapshot(record)
        self._notify(snapshot, "task.started")
        return snapshot

    def succeed(self, task_id: str, result: Any = None) -> TaskRecord:
        """Mark a running task successful and store an isolated result snapshot."""
        with self._lock:
            record = self._require(task_id)
            transition_task(record, TaskStatus.SUCCEEDED, result=deepcopy(result))
            duration = self._finish_duration(task_id)
            snapshot = self._snapshot(record)
        self._notify(snapshot, "task.succeeded", duration_ms=duration)
        return snapshot

    def fail(self, task_id: str, error: str) -> TaskRecord:
        """Mark a running task failed without writing the raw error to logs."""
        if not isinstance(error, str) or not error.strip():
            raise ValueError("error must be a non-empty string")
        with self._lock:
            record = self._require(task_id)
            transition_task(record, TaskStatus.FAILED, error=error)
            duration = self._finish_duration(task_id)
            snapshot = self._snapshot(record)
        self._notify(
            snapshot,
            "task.failed",
            duration_ms=duration,
            details={"error_present": True, "error_length": len(error.strip())},
        )
        return snapshot

    def cancel(self, task_id: str) -> TaskRecord:
        """Cancel a pending or running task."""
        with self._lock:
            record = self._require(task_id)
            transition_task(record, TaskStatus.CANCELLED)
            duration = self._finish_duration(task_id)
            snapshot = self._snapshot(record)
        self._notify(snapshot, "task.cancelled", duration_ms=duration)
        return snapshot

    def get(self, task_id: str) -> TaskRecord | None:
        """Return a deep snapshot so callers cannot mutate stored task data."""
        with self._lock:
            record = self._tasks.get(task_id)
            return self._snapshot(record) if record is not None else None

    def list_tasks(self) -> list[TaskRecord]:
        """Return deep snapshots of all tasks in insertion order."""
        with self._lock:
            return [self._snapshot(record) for record in self._tasks.values()]

    def _require(self, task_id: str) -> TaskRecord:
        record = self._tasks.get(task_id)
        if record is None:
            raise KeyError(f"Unknown task: {task_id}")
        return record

    @staticmethod
    def _snapshot(record: TaskRecord) -> TaskRecord:
        return replace(
            record,
            result=deepcopy(record.result),
            metadata=deepcopy(record.metadata),
        )

    def _finish_duration(self, task_id: str) -> float | None:
        started = self._started_at.pop(task_id, None)
        if started is None:
            return None
        return round(max(0.0, monotonic() - started) * 1000, 3)

    def _notify(
        self,
        record: TaskRecord,
        event: str,
        *,
        duration_ms: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        try:
            self._logger.emit(
                event,
                task_id=record.task_id,
                status=record.status.value,
                duration_ms=duration_ms,
                details=details or {},
            )
        except Exception:
            # Logging must not prevent a valid task state transition.
            pass
        self._event_bus.publish(
            event,
            {"task_id": record.task_id, "status": record.status.value},
        )
