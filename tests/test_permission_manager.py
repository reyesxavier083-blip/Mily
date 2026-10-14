"""Unit tests for MILY's explicit tool authorization boundary."""

import unittest

from mily_core.permission_manager import (
    PermissionDecision,
    PermissionManager,
    ToolRisk,
)


class PermissionManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = PermissionManager(
            {
                "read_project_file": ToolRisk.READ_ONLY,
                "write_project_file": ToolRisk.WRITE,
                "send_external_request": ToolRisk.EXTERNAL,
                "delete_project_file": ToolRisk.DESTRUCTIVE,
            }
        )

    def test_allowlisted_read_only_tool_is_allowed(self) -> None:
        result = self.manager.authorize("read_project_file", ToolRisk.READ_ONLY)
        self.assertEqual(result.decision, PermissionDecision.ALLOW)
        self.assertTrue(result.allowed)

    def test_unknown_tool_is_denied(self) -> None:
        result = self.manager.authorize("run_shell", ToolRisk.READ_ONLY)
        self.assertEqual(result.decision, PermissionDecision.DENY)
        self.assertFalse(result.allowed)

    def test_risk_mismatch_is_denied(self) -> None:
        result = self.manager.authorize("read_project_file", ToolRisk.DESTRUCTIVE)
        self.assertEqual(result.decision, PermissionDecision.DENY)

    def test_write_requires_confirmation(self) -> None:
        result = self.manager.authorize("write_project_file", ToolRisk.WRITE)
        self.assertEqual(result.decision, PermissionDecision.REQUIRE_CONFIRMATION)
        self.assertFalse(result.allowed)

    def test_confirmation_allows_only_registered_write_tool(self) -> None:
        result = self.manager.authorize(
            "write_project_file", ToolRisk.WRITE, confirmed=True
        )
        self.assertEqual(result.decision, PermissionDecision.ALLOW)

    def test_confirmation_is_not_remembered_between_calls(self) -> None:
        approved = self.manager.authorize(
            "write_project_file", ToolRisk.WRITE, confirmed=True
        )
        next_call = self.manager.authorize("write_project_file", ToolRisk.WRITE)
        self.assertEqual(approved.decision, PermissionDecision.ALLOW)
        self.assertEqual(
            next_call.decision, PermissionDecision.REQUIRE_CONFIRMATION
        )

    def test_external_operation_requires_fresh_confirmation(self) -> None:
        result = self.manager.authorize("send_external_request", ToolRisk.EXTERNAL)
        self.assertEqual(result.decision, PermissionDecision.REQUIRE_CONFIRMATION)

    def test_destructive_operation_requires_fresh_confirmation(self) -> None:
        result = self.manager.authorize("delete_project_file", ToolRisk.DESTRUCTIVE)
        self.assertEqual(result.decision, PermissionDecision.REQUIRE_CONFIRMATION)

    def test_confirmation_does_not_authorize_unknown_tool(self) -> None:
        result = self.manager.authorize(
            "unregistered_tool", ToolRisk.WRITE, confirmed=True
        )
        self.assertEqual(result.decision, PermissionDecision.DENY)

    def test_non_boolean_confirmation_is_denied(self) -> None:
        result = self.manager.authorize(
            "write_project_file", ToolRisk.WRITE, confirmed=1  # type: ignore[arg-type]
        )
        self.assertEqual(result.decision, PermissionDecision.DENY)

    def test_invalid_registry_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            PermissionManager({"Run Shell": ToolRisk.READ_ONLY})  # type: ignore[dict-item]
        with self.assertRaises(ValueError):
            PermissionManager({"read_file": "read_only"})  # type: ignore[dict-item]


if __name__ == "__main__":
    unittest.main()
