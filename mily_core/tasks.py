"""Small, dependency-free task state machine for MILY.

This module tracks task lifecycle only. It deliberately does not execute tools;
execution and authorization should remain separate layers.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


_TERMINAL_STATUSES = {
    TaskStatus.SUCCEEDED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
}
_ALLOWED_TRANSITIONS = {
    TaskStatus.PENDING: {TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.RUNNING: _TERMINAL_STATUSES,
    TaskStatus.SUCCEEDED: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELLED: set(),
}


@dataclass
class TaskRecord:
    """A task's observable state, result, and safe error summary."""

    task_id: str
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.task_id, str) or not self.task_id.strip():
            raise ValueError("task_id must be a non-empty string")


def transition_task(
    task: TaskRecord,
    new_status: TaskStatus,
    *,
    result: Any = None,
    error: str | None = None,
) -> TaskRecord:
    """Apply a valid lifecycle transition and return the updated task.

    Callers must authorize actions before invoking tools; this state machine
    does not grant permissions or run any external operation.
    """
    if not isinstance(new_status, TaskStatus):
        raise ValueError("new_status must be a TaskStatus value")
    if new_status not in _ALLOWED_TRANSITIONS[task.status]:
        raise ValueError(
            f"Invalid task transition: {task.status.value} -> {new_status.value}"
        )
    if new_status == TaskStatus.SUCCEEDED and error:
        raise ValueError("A succeeded task cannot contain an error")
    if new_status == TaskStatus.FAILED and not (error and error.strip()):
        raise ValueError("A failed task requires a non-empty error summary")

    task.status = new_status
    if new_status == TaskStatus.SUCCEEDED:
        task.result = result
        task.error = None
    elif new_status == TaskStatus.FAILED:
        task.result = None
        task.error = error.strip()[:500]
    elif new_status == TaskStatus.CANCELLED:
        task.result = None
        task.error = None
    return task
