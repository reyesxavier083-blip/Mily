"""Tests for the LEYRA TOOLS ENGINE."""

from __future__ import annotations

import unittest

from leyra_core.tools import ToolError, ToolRegistry, ToolStatus, build_default_registry


class RegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = build_default_registry()

    def test_listing_includes_availability(self) -> None:
        entries = {entry["name"]: entry for entry in self.registry.list()}
        self.assertTrue(entries["calculator.expression"]["available"])
        self.assertFalse(entries["web.search"]["available"])
        self.assertTrue(entries["web.search"]["unavailableReason"])
        self.assertEqual(entries["web.search"]["risk"], "external")

    def test_unknown_tool_is_invalid(self) -> None:
        result = self.registry.execute("nope.nothing", {})
        self.assertEqual(result.status, ToolStatus.INVALID)

    def test_duplicate_registration_rejected(self) -> None:
        from leyra_core.tools import Tool, ToolSpec
        from mily_core.permission_manager import ToolRisk

        duplicate = Tool(ToolSpec(name="calculator.expression", title="dup", description="",
                                  risk=ToolRisk.READ_ONLY), handler=lambda _: None)
        with self.assertRaises(ToolError):
            self.registry.register(duplicate)


class CalculatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = build_default_registry()

    def run_calc(self, expression: str):
        return self.registry.execute("calculator.expression", {"expression": expression})

    def test_arithmetic(self) -> None:
        result = self.run_calc("(18/100)*2450 + sqrt(16)")
        self.assertEqual(result.status, ToolStatus.OK)
        self.assertAlmostEqual(result.output["value"], 445.0)

    def test_functions_and_constants(self) -> None:
        result = self.run_calc("round(cos(pi), 3)")
        self.assertEqual(result.output["value"], -1.0)

    def test_rejects_code_execution(self) -> None:
        for expression in ("__import__('os').system('ls')", "open('/etc/passwd').read()",
                           "[1,2,3]", "lambda: 1", "2**999999"):
            result = self.run_calc(expression)
            self.assertNotEqual(result.status, ToolStatus.OK, expression)

    def test_rejects_division_by_zero(self) -> None:
        result = self.run_calc("1/0")
        self.assertEqual(result.status, ToolStatus.INVALID)

    def test_rejects_long_expression(self) -> None:
        result = self.run_calc("1+" * 400 + "1")
        self.assertEqual(result.status, ToolStatus.INVALID)


class ConversionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = build_default_registry()

    def test_length(self) -> None:
        result = self.registry.execute("units.convert",
                                      {"value": 10, "from": "km", "to": "mi", "category": "longitud"})
        self.assertAlmostEqual(result.output["result"], 6.2137, places=3)

    def test_invalid_unit(self) -> None:
        result = self.registry.execute("units.convert",
                                      {"value": 1, "from": "km", "to": "lightyear", "category": "longitud"})
        self.assertEqual(result.status, ToolStatus.INVALID)

    def test_temperature(self) -> None:
        result = self.registry.execute("units.temperature", {"value": 100, "from": "C", "to": "F"})
        self.assertAlmostEqual(result.output["result"], 212.0)

    def test_boolean_is_not_a_number(self) -> None:
        result = self.registry.execute("units.temperature", {"value": True, "from": "C", "to": "F"})
        self.assertEqual(result.status, ToolStatus.INVALID)


class DataToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = build_default_registry()

    def test_summary(self) -> None:
        result = self.registry.execute("data.summary", {"values": [2, 4, 4, 4, 5, 5, 7, 9]})
        self.assertEqual(result.status, ToolStatus.OK)
        self.assertAlmostEqual(result.output["mean"], 5.0)
        self.assertAlmostEqual(result.output["stdev"], 2.0)
        self.assertEqual(len(result.output["histogram"]), 8)

    def test_rejects_text_values(self) -> None:
        result = self.registry.execute("data.summary", {"values": ["a"]})
        self.assertEqual(result.status, ToolStatus.INVALID)

    def test_text_stats(self) -> None:
        result = self.registry.execute("text.stats", {"text": "uno dos tres\ncuatro"})
        self.assertEqual(result.output["words"], 4)
        self.assertEqual(result.output["lines"], 2)

    def test_json_pretty_invalid(self) -> None:
        result = self.registry.execute("json.pretty", {"data": "{not json"})
        self.assertEqual(result.status, ToolStatus.INVALID)


class PermissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = build_default_registry()

    def test_external_tool_requires_confirmation(self) -> None:
        result = self.registry.execute("web.search", {"query": "leyra"}, confirmed=False)
        self.assertEqual(result.status, ToolStatus.CONFIRMATION_REQUIRED)

    def test_unavailable_external_tool_is_honest(self) -> None:
        result = self.registry.execute("web.search", {"query": "leyra"}, confirmed=True)
        self.assertEqual(result.status, ToolStatus.UNAVAILABLE)
        self.assertIn("proveedor", result.detail)

    def test_currency_requires_provider(self) -> None:
        result = self.registry.execute("currency.convert",
                                      {"amount": 10, "from": "USD", "to": "MXN"}, confirmed=True)
        self.assertEqual(result.status, ToolStatus.UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
