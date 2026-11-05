"""Tests for the SQLite storage used by conversations, memory and settings."""

from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from leyra_core.storage import Store


class StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.folder.name) / "leyra.db")

    def tearDown(self) -> None:
        self.store.close()
        self.folder.cleanup()

    def test_conversation_lifecycle(self) -> None:
        conversation = self.store.create_conversation("Prueba", project="Demo")
        self.store.add_message(conversation["id"], "user", "Hola LEYRA")
        self.store.add_message(conversation["id"], "assistant", "Hola, ¿en qué ayudo?")
        loaded = self.store.get_conversation(conversation["id"])
        self.assertEqual(len(loaded["messages"]), 2)
        self.assertEqual(loaded["project"], "Demo")
        self.assertTrue(self.store.rename_conversation(conversation["id"], "Renombrada"))
        self.assertTrue(self.store.set_pinned(conversation["id"], True))
        self.assertEqual(self.store.list_conversations()[0]["title"], "Renombrada")
        self.assertTrue(self.store.delete_conversation(conversation["id"]))
        self.assertIsNone(self.store.get_conversation(conversation["id"]))

    def test_search_matches_content(self) -> None:
        conversation = self.store.create_conversation("Otra")
        self.store.add_message(conversation["id"], "user", "necesito revisar el presupuesto")
        results = self.store.list_conversations(query="presupuesto")
        self.assertEqual(len(results), 1)
        self.assertEqual(self.store.list_conversations(query="inexistente"), [])

    def test_invalid_role_rejected(self) -> None:
        conversation = self.store.create_conversation()
        with self.assertRaises(ValueError):
            self.store.add_message(conversation["id"], "root", "x")

    def test_memory_deduplication(self) -> None:
        first = self.store.upsert_memory("Prefiere respuestas breves", category="preferencia")
        second = self.store.upsert_memory("  prefiere   respuestas breves ", category="preferencia")
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(self.store.list_memories()), 1)
        self.assertTrue(self.store.delete_memory(first["id"]))
        self.assertEqual(self.store.list_memories(), [])

    def test_empty_memory_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.store.upsert_memory("   ")

    def test_settings_roundtrip(self) -> None:
        self.store.set_setting("voice", {"rate": 1.2})
        self.assertEqual(self.store.get_setting("voice")["rate"], 1.2)
        self.assertEqual(self.store.get_setting("missing", "fallback"), "fallback")

    def test_integration_log_and_stats(self) -> None:
        self.store.log_integration("com.whatsapp", "link", "nivel 2")
        self.assertEqual(self.store.integration_history()[0]["packageName"], "com.whatsapp")
        stats = self.store.stats()
        self.assertIn("conversations", stats)
        self.assertGreaterEqual(stats["sizeBytes"], 0)

    def test_messages_are_bounded(self) -> None:
        conversation = self.store.create_conversation()
        message = self.store.add_message(conversation["id"], "user", "x" * 200000)
        self.assertLessEqual(len(message["content"]), 120000)


if __name__ == "__main__":
    unittest.main()
