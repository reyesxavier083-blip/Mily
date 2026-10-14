"""Tests for the MILY task lifecycle state machine."""

import unittest

from mily_core.tasks import TaskRecord, TaskStatus, transition_task


class TaskTransitionTests(unittest.TestCase):
    def test_happy_path(self) -> None:
        task = TaskRecord("task-1")
        transition_task(task, TaskStatus.RUNNING)
        transition_task(task, TaskStatus.SUCCEEDED, result={"ok": True})
        self.assertEqual(task.status, TaskStatus.SUCCEEDED)
        self.assertEqual(task.result, {"ok": True})

    def test_pending_can_be_cancelled(self) -> None:
        task = TaskRecord("task-2")
        transition_task(task, TaskStatus.CANCELLED)
        self.assertEqual(task.status, TaskStatus.CANCELLED)

    def test_cannot_skip_running(self) -> None:
        task = TaskRecord("task-3")
        with self.assertRaises(ValueError):
            transition_task(task, TaskStatus.SUCCEEDED)

    def test_terminal_state_cannot_change(self) -> None:
        task = TaskRecord("task-4")
        transition_task(task, TaskStatus.RUNNING)
        transition_task(task, TaskStatus.CANCELLED)
        with self.assertRaises(ValueError):
            transition_task(task, TaskStatus.RUNNING)

    def test_failure_requires_error_summary(self) -> None:
        task = TaskRecord("task-5")
        transition_task(task, TaskStatus.RUNNING)
        with self.assertRaises(ValueError):
            transition_task(task, TaskStatus.FAILED)

    def test_failure_error_is_bounded(self) -> None:
        task = TaskRecord("task-6")
        transition_task(task, TaskStatus.RUNNING)
        transition_task(task, TaskStatus.FAILED, error="x" * 1000)
        self.assertEqual(len(task.error or ""), 500)

    def test_task_id_must_not_be_empty(self) -> None:
        with self.assertRaises(ValueError):
            TaskRecord("  ")


if __name__ == "__main__":
    unittest.main()
