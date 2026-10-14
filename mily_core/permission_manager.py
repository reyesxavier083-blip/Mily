"""Explicit authorization decisions for MILY tool execution.

This module does not execute tools or remember approvals. Every non-read-only
operation needs a fresh, explicit confirmation from the caller.
"""

from dataclasses import dataclass
from enum import Enum
import re
from typing import Mapping


class ToolRisk(str, Enum):
    """Risk category declared by the trusted tool registry."""

    READ_ONLY = "read_only"
    WRITE = "write"
    EXTERNAL = "external"
    DESTRUCTIVE = "destructive"


class PermissionDecision(str, Enum):
    """Result of checking whether a tool call may proceed."""

    ALLOW = "allow"
    REQUIRE_CONFIRMATION = "require_confirmation"
    DENY = "deny"


@dataclass(frozen=True)
class AuthorizationResult:
    """Immutable authorization result with a safe, user-facing reason."""

    decision: PermissionDecision
    tool_name: str
    reason: str

    @property
    def allowed(self) -> bool:
        """Whether the caller may execute the operation now."""
        return self.decision is PermissionDecision.ALLOW


_TOOL_NAME = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")


class PermissionManager:
    """Check calls against a trusted allowlist and require confirmation for risk.

    The allowlist is supplied by application configuration, not by model output.
    This manager deliberately has no persistence and does not grant permissions
    based on a generated plan, a task state, or a tool's own request.
    """

    def __init__(self, allowed_tools: Mapping[str, ToolRisk] | None = None) -> None:
        registry: dict[str, ToolRisk] = {}
        for name, risk in (allowed_tools or {}).items():
            if not isinstance(name, str) or not _TOOL_NAME.fullmatch(name):
                raise ValueError("Tool names must be valid lowercase identifiers")
            if not isinstance(risk, ToolRisk):
                raise ValueError(f"Risk for tool '{name}' must be a ToolRisk")
            if name in registry:
                raise ValueError(f"Duplicate tool registration: {name}")
            registry[name] = risk
        self._allowed_tools = registry

    def authorize(
        self,
        tool_name: str,
        risk: ToolRisk,
        *,
        confirmed: bool = False,
    ) -> AuthorizationResult:
        """Return a decision; never executes the requested operation."""
        if not isinstance(tool_name, str) or not _TOOL_NAME.fullmatch(tool_name):
            return AuthorizationResult(
                PermissionDecision.DENY,
                str(tool_name)[:64],
                "Invalid tool identifier.",
            )
        if not isinstance(risk, ToolRisk):
            return AuthorizationResult(
                PermissionDecision.DENY,
                tool_name,
                "Unknown or invalid risk category.",
            )
        if type(confirmed) is not bool:
            return AuthorizationResult(
                PermissionDecision.DENY,
                tool_name,
                "Confirmation must be an explicit boolean.",
            )

        registered_risk = self._allowed_tools.get(tool_name)
        if registered_risk is None:
            return AuthorizationResult(
                PermissionDecision.DENY,
                tool_name,
                "Tool is not in the trusted allowlist.",
            )
        if registered_risk is not risk:
            return AuthorizationResult(
                PermissionDecision.DENY,
                tool_name,
                "Requested risk does not match the trusted tool registry.",
            )
        if risk is ToolRisk.READ_ONLY:
            return AuthorizationResult(
                PermissionDecision.ALLOW,
                tool_name,
                "Read-only tool is allowlisted.",
            )
        if not confirmed:
            return AuthorizationResult(
                PermissionDecision.REQUIRE_CONFIRMATION,
                tool_name,
                "This operation requires explicit confirmation for this call.",
            )
        return AuthorizationResult(
            PermissionDecision.ALLOW,
            tool_name,
            "Explicit confirmation received for this call.",
        )
