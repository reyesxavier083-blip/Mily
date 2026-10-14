"""Tests for MILY's task lifecycle coordinator."""

import json
import logging
import unittest
from io import StringIO

from mily_core.event_bus import EventBus
from mily_core.observability import StructuredLogger
from mily_core.task_manager import TaskManager
from mily_core.tasks import TaskStatus


class TaskManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stream = StringIO()
        logger = logging.Logger("mily-task-manager-test", level=logging.INFO)
        logger.addHandler(logging.StreamHandler(self.stream))
        self.events = []
        self.bus = EventBus()
        self.bus.subscribe("task.created", lambda name, payload: self.events.append((name, payload)))
        self.bus.subscribe("task.started", lambda name, payload: self.events.append((name, payload)))
        self.bus.subscribe("task.succeeded", lambda name, payload: self.events.append((name, payload)))
        self.bus.subscribe("task.failed", lambda name, payload: self.events.append((name, payload)))
        self.bus.subscribe("task.cancelled", lambda name, payload: self.events.append((name, payload)))
        self.manager = TaskManager(
            event_bus=self.bus,
            logger=StructuredLogger(logger),
        )

    def test_successful_lifecycle_emits_events_and_duration(self) -> None:
        created = self.manager.create("t-1", metadata={"source": "test"})
        self.assertEqual(created.status, TaskStatus.PENDING)
        self.manager.start("t-1")
        completed = self.manager.succeed("t-1", result={"ok": True})

        self.assertEqual(completed.status, TaskStatus.SUCCEEDED)
        self.assertEqual(completed.result, {"ok": True})
        self.assertEqual([event for event, _ in self.events],
                         ["task.created", "task.started", "task.succeeded"])
        records = [json.loads(line) for line in self.stream.getvalue().splitlines()]
        self.assertEqual(records[-1]["event"], "task.succeeded")
        self.assertIsInstance(records[-1]["duration_ms"], (int, float))
        self.assertGreaterEqual(records[-1]["duration_ms"], 0)

    def test_failed_task_does_not_log_raw_error(self) -> None:
        self.manager.create("t-2")
        self.manager.start("t-2")
        self.manager.fail("t-2", "password=secret-private-value")
        self.assertNotIn("secret-private-value", self.stream.getvalue())
        record = json.loads(self.stream.getvalue().splitlines()[-1])
        self.assertTrue(record["details"]["error_present"])

    def test_cancel_pending_task(self) -> None:
        self.manager.create("t-3")
        cancelled = self.manager.cancel("t-3")
        self.assertEqual(cancelled.status, TaskStatus.CANCELLED)

    def test_duplicate_and_unknown_ids_are_rejected(self) -> None:
        self.manager.create("t-4")
        with self.assertRaises(ValueError):
            self.manager.create("t-4")
        with self.assertRaises(KeyError):
            self.manager.start("missing")

    def test_invalid_transitions_remain_rejected(self) -> None:
        self.manager.create("t-5")
        with self.assertRaises(ValueError):
            self.manager.succeed("t-5")
        self.assertEqual(self.manager.get("t-5").status, TaskStatus.PENDING)

    def test_snapshot_does_not_allow_status_mutation(self) -> None:
        self.manager.create("t-6", metadata={"mode": "safe"})
        snapshot = self.manager.get("t-6")
        snapshot.status = TaskStatus.FAILED
        snapshot.metadata["mode"] = "changed"
        stored = self.manager.get("t-6")
        self.assertEqual(stored.status, TaskStatus.PENDING)
        self.assertEqual(stored.metadata["mode"], "safe")

    def test_requires_non_empty_error(self) -> None:
        self.manager.create("t-7")
        self.manager.start("t-7")
        with self.assertRaises(ValueError):
            self.manager.fail("t-7", "  ")
        self.assertEqual(self.manager.get("t-7").status, TaskStatus.RUNNING)


if __name__ == "__main__":
    unittest.main()
