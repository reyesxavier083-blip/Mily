"""Tests for shared voice settings and text preparation."""

from __future__ import annotations

import unittest

from leyra_core.voice import (
    VoiceError,
    VoiceSettings,
    chunk_text,
    estimate_seconds,
    expressive_text,
    load_settings,
)


class FakeStore:
    def __init__(self, payload=None) -> None:
        self.payload = payload

    def get_setting(self, key, default=None):
        return self.payload if self.payload is not None else default


class SettingsTests(unittest.TestCase):
    def test_defaults_are_valid(self) -> None:
        settings = VoiceSettings()
        self.assertEqual(settings.language, "es-MX")
        self.assertTrue(settings.barge_in)

    def test_bounds(self) -> None:
        for kwargs in ({"rate": 0.2}, {"rate": 3}, {"pitch": -1}, {"volume": 2},
                       {"language": "xx-YY"}, {"style": "raro"}, {"rate": "1.0"}):
            with self.assertRaises(VoiceError, msg=str(kwargs)):
                VoiceSettings(**kwargs)

    def test_boolean_flags_must_be_booleans(self) -> None:
        with self.assertRaises(VoiceError):
            VoiceSettings(auto_speak="yes")

    def test_roundtrip(self) -> None:
        settings = VoiceSettings(voice_name="Leyra", rate=1.25, style="calma")
        restored = VoiceSettings.from_dict(settings.to_dict())
        self.assertEqual(restored, settings)

    def test_load_settings_falls_back(self) -> None:
        self.assertEqual(load_settings(FakeStore()).language, "es-MX")
        self.assertEqual(load_settings(FakeStore({"rate": 99})).rate, 1.0)
        self.assertEqual(load_settings(FakeStore({"rate": 1.4})).rate, 1.4)


class TextTests(unittest.TestCase):
    def test_chunking_respects_limit(self) -> None:
        text = ("Frase corta. " * 60).strip()
        chunks = chunk_text(text, max_chars=120)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 120 for chunk in chunks))
        self.assertEqual(" ".join(chunks).replace("  ", " "), text.replace("  ", " "))

    def test_chunking_handles_long_words(self) -> None:
        chunks = chunk_text("x" * 500, max_chars=80)
        self.assertTrue(all(len(chunk) <= 80 for chunk in chunks))

    def test_chunk_limits(self) -> None:
        with self.assertRaises(VoiceError):
            chunk_text("hola", max_chars=10)
        self.assertEqual(chunk_text("   "), [])

    def test_expressive_pauses_keep_words(self) -> None:
        settings = VoiceSettings()
        cleaned = expressive_text("Hola!!! ¿Qué tal?   Bien...", settings)
        self.assertNotIn("!!!", cleaned)
        self.assertIn("Hola", cleaned)
        self.assertIn("Bien", cleaned)

    def test_estimate_grows_with_length(self) -> None:
        settings = VoiceSettings()
        short = estimate_seconds("Hola.", settings)
        long = estimate_seconds("Hola. " * 40, settings)
        self.assertGreater(long, short)


if __name__ == "__main__":
    unittest.main()
