"""Tests for MILY's in-process event bus."""

import json
import logging
import unittest
from io import StringIO

from mily_core.event_bus import EventBus
from mily_core.observability import StructuredLogger


class EventBusTests(unittest.TestCase):
    def test_publishes_to_subscribers(self) -> None:
        bus = EventBus()
        received = []
        bus.subscribe("task.done", lambda name, payload: received.append((name, payload)))

        errors = bus.publish("task.done", {"task_id": "t-1"})

        self.assertEqual(errors, ())
        self.assertEqual(received, [("task.done", {"task_id": "t-1"})])

    def test_does_not_send_to_other_event_names(self) -> None:
        bus = EventBus()
        received = []
        bus.subscribe("task.done", lambda name, payload: received.append(payload))
        bus.publish("memory.saved", "hello")
        self.assertEqual(received, [])

    def test_unsubscribe_is_idempotent(self) -> None:
        bus = EventBus()
        received = []
        unsubscribe = bus.subscribe("tick", lambda name, payload: received.append(payload))
        unsubscribe()
        unsubscribe()
        bus.publish("tick", 1)
        self.assertEqual(received, [])
        self.assertEqual(bus.subscriber_count("tick"), 0)

    def test_handler_failure_does_not_block_other_handlers(self) -> None:
        bus = EventBus()
        received = []

        def broken(name, payload):
            raise RuntimeError("handler failed")

        bus.subscribe("event", broken)
        bus.subscribe("event", lambda name, payload: received.append(payload))
        errors = bus.publish("event", 42)

        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], RuntimeError)
        self.assertEqual(received, [42])

    def test_logs_dispatch_metadata_without_payload(self) -> None:
        stream = StringIO()
        logger = logging.Logger("mily-event-test", level=logging.INFO)
        logger.addHandler(logging.StreamHandler(stream))
        bus = EventBus(logger=StructuredLogger(logger))

        bus.publish("private.event", {"message": "private user content"})

        record = json.loads(stream.getvalue().strip())
        self.assertEqual(record["event"], "event.dispatched")
        self.assertEqual(record["details"]["name"], "private.event")
        self.assertEqual(record["details"]["subscriber_count"], 0)
        self.assertNotIn("private user content", stream.getvalue())

    def test_rejects_invalid_event_name(self) -> None:
        bus = EventBus()
        with self.assertRaises(ValueError):
            bus.publish(" ")
        with self.assertRaises(ValueError):
            bus.subscribe("", lambda name, payload: None)

    def test_rejects_non_callable_handler(self) -> None:
        with self.assertRaises(TypeError):
            EventBus().subscribe("event", None)


if __name__ == "__main__":
    unittest.main()
