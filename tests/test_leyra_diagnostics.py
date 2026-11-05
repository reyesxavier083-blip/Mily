"""Tests for the diagnostics hub aggregation."""

from __future__ import annotations

import unittest

from leyra_core.diagnostics import DiagnosticsHub, Health, ModuleHealth


class HubTests(unittest.TestCase):
    def test_empty_hub_is_ok(self) -> None:
        self.assertEqual(DiagnosticsHub().run()["status"], "ok")

    def test_worst_status_wins(self) -> None:
        hub = DiagnosticsHub()
        hub.register("a", lambda: ModuleHealth("a", Health.OK, "fine"))
        hub.register("b", lambda: ModuleHealth("b", Health.DEGRADED, "partial"))
        hub.register("c", lambda: ModuleHealth("c", Health.UNAVAILABLE, "off"))
        report = hub.run()
        self.assertEqual(report["status"], "unavailable")
        self.assertEqual(report["counts"]["ok"], 1)
        self.assertEqual(report["counts"]["degraded"], 1)

    def test_exception_becomes_error_not_green(self) -> None:
        hub = DiagnosticsHub()
        def boom() -> ModuleHealth:
            raise RuntimeError("no disponible")
        hub.register("boom", boom)
        report = hub.run()
        self.assertEqual(report["status"], "error")
        self.assertEqual(report["modules"][0]["status"], "error")
        self.assertNotIn("no disponible", report["modules"][0]["detail"])

    def test_engine_registration_uses_health(self) -> None:
        class Engine:
            def health(self):
                return {"status": "degraded", "detail": "sin puente", "linked": 0}
        hub = DiagnosticsHub()
        hub.register_engine("apps", Engine())
        module = hub.run()["modules"][0]
        self.assertEqual(module["status"], "degraded")
        self.assertEqual(module["data"]["linked"], 0)
        self.assertIn("durationMs", module["data"])


if __name__ == "__main__":
    unittest.main()
