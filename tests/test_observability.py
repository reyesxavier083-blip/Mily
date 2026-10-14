"""Tests for MILY structured logging and credential redaction."""

import json
import logging
import unittest
from io import StringIO

from mily_core.observability import StructuredLogger


class StructuredLoggerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stream = StringIO()
        self.logger = logging.Logger("mily-test", level=logging.INFO)
        handler = logging.StreamHandler(self.stream)
        handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger.addHandler(handler)
        self.subject = StructuredLogger(self.logger)

    def event(self, **kwargs):
        self.subject.emit("task.finished", **kwargs)
        return json.loads(self.stream.getvalue().strip().splitlines()[-1])

    def test_emits_valid_json_with_task_metadata(self) -> None:
        record = self.event(
            task_id="task-42", status="succeeded", duration_ms=12.5,
            details={"steps": 3},
        )
        self.assertEqual(record["event"], "task.finished")
        self.assertEqual(record["task_id"], "task-42")
        self.assertEqual(record["status"], "succeeded")
        self.assertEqual(record["duration_ms"], 12.5)
        self.assertEqual(record["details"], {"steps": 3})
        self.assertTrue(record["timestamp"])

    def test_redacts_sensitive_keys_recursively(self) -> None:
        record = self.event(details={
            "api_key": "sk-12345678901234567890",
            "nested": {"password": "not-for-logs", "ok": "fine"},
        })
        encoded = json.dumps(record)
        self.assertNotIn("sk-12345678901234567890", encoded)
        self.assertNotIn("not-for-logs", encoded)
        self.assertIn("[REDACTED]", encoded)
        self.assertEqual(record["details"]["nested"]["ok"], "fine")

    def test_redacts_credentials_inside_text(self) -> None:
        record = self.event(details={
            "message": "request failed with Bearer abcdefghijklmnop",
            "hint": "api_key=secret-value",
        })
        encoded = json.dumps(record)
        self.assertNotIn("abcdefghijklmnop", encoded)
        self.assertNotIn("secret-value", encoded)

    def test_rejects_invalid_event_and_duration(self) -> None:
        with self.assertRaises(ValueError):
            self.subject.emit(" ")
        with self.assertRaises(ValueError):
            self.subject.emit("task", duration_ms=-1)
        with self.assertRaises(ValueError):
            self.subject.emit("task", duration_ms=float("nan"))
        with self.assertRaises(TypeError):
            self.subject.emit("task", details=["not", "a", "mapping"])

    def test_bounds_large_details(self) -> None:
        record = self.event(details={f"k{i}": i for i in range(60)})
        self.assertTrue(record["details"]["_truncated"])
        self.assertLessEqual(len(record["details"]), 51)


if __name__ == "__main__":
    unittest.main()
