"""Data model for the LEYRA Android APP INTEGRATION ENGINE.

The engine is platform-agnostic on purpose: it decides *what* integration is
allowed and *which* public Android mechanism would carry it out. The actual
dispatch happens in a platform bridge (Android PackageManager/Intent layer),
which is injected. Nothing in this module touches the network, the filesystem
of other apps, or private application data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any, Mapping

_PACKAGE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z0-9_]+){1,}$")
_CONNECTOR_ID = re.compile(r"^[a-z][a-z0-9_.-]{1,63}$")
_SEMVER = re.compile(r"^[0-9]+(\.[0-9]+){0,3}([-+][0-9A-Za-z.-]{1,16})?$")
_PERMISSION = re.compile(r"^[A-Za-z0-9_.:-]{2,120}$")


class IntegrationLevel(int, Enum):
    """Levels defined by the master specification (section 4.3).

    The level is the *strongest* public mechanism a connector is allowed to use.
    Levels never grant access to another app's private storage.
    """

    OPEN = 1
    INTEROP = 2
    API = 3
    PLUGIN = 4
    ACCESSIBILITY = 5


class CapabilityStatus(str, Enum):
    """Whether an app can be used by LEYRA at a given level."""

    FULL = "full"
    PARTIAL = "partial"
    OPEN_ONLY = "open_only"
    INCOMPATIBLE = "incompatible"


class ActionKind(str, Enum):
    """Public Android mechanism that carries an action out."""

    LAUNCH = "launch"
    INTENT = "intent"
    DEEP_LINK = "deep_link"
    APP_LINK = "app_link"
    SHARE = "share"
    CONTENT_PROVIDER = "content_provider"
    SHORTCUT = "shortcut"
    PLUGIN = "plugin"
    ACCESSIBILITY = "accessibility"


class AuthMethod(str, Enum):
    NONE = "none"
    DEEP_LINK = "deep_link"
    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    SDK = "sdk"


class ParamType(str, Enum):
    STRING = "string"
    TEXT = "text"
    URL = "url"
    FILE = "file"
    NUMBER = "number"
    BOOLEAN = "boolean"


PARAM_TYPES = {item.value for item in ParamType}
ACTION_KINDS = {item.value for item in ActionKind}
AUTH_METHODS = {item.value for item in AuthMethod}


class IntegrationError(ValueError):
    """Raised when a manifest, permission or action request is invalid."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise IntegrationError(message)


@dataclass(frozen=True)
class ActionParameter:
    """A single documented parameter of a connector action."""

    name: str
    type: ParamType
    description: str = ""
    required: bool = True

    def __post_init__(self) -> None:
        _require(bool(_CONNECTOR_ID.fullmatch(self.name)), f"Invalid parameter name: {self.name!r}")
        _require(self.type in set(ParamType), f"Invalid parameter type: {self.type!r}")
        _require(len(self.description) <= 240, "Parameter description is too long")

    def coerce(self, value: Any) -> Any:
        """Validate and normalize a caller-supplied value for this parameter."""
        _require(value is not None, f"Parameter '{self.name}' is required")
        if self.type is ParamType.BOOLEAN:
            if isinstance(value, bool):
                return value
            if isinstance(value, str) and value.lower() in {"true", "false"}:
                return value.lower() == "true"
            raise IntegrationError(f"Parameter '{self.name}' must be a boolean")
        if self.type is ParamType.NUMBER:
            if isinstance(value, bool):
                raise IntegrationError(f"Parameter '{self.name}' must be a number")
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise IntegrationError(f"Parameter '{self.name}' must be a number") from exc
            return int(number) if number.is_integer() else number
        text = value if isinstance(value, str) else str(value)
        _require(len(text) <= 4000, f"Parameter '{self.name}' exceeds the size limit")
        if self.type in (ParamType.STRING, ParamType.TEXT, ParamType.URL, ParamType.FILE):
            _require(text.strip() != "", f"Parameter '{self.name}' cannot be empty")
        if self.type is ParamType.URL:
            _require(re.match(r"^https?://[^\s]+$", text) is not None, f"Parameter '{self.name}' must be an http(s) URL")
        return text


@dataclass(frozen=True)
class ConnectorAction:
    """A capability an app publicly exposes to other apps."""

    id: str
    label: str
    kind: ActionKind
    level: IntegrationLevel
    description: str = ""
    parameters: tuple[ActionParameter, ...] = ()
    permissions: tuple[str, ...] = ()
    destructive: bool = False

    def __post_init__(self) -> None:
        _require(bool(_CONNECTOR_ID.fullmatch(self.id)), f"Invalid action id: {self.id!r}")
        _require(self.label.strip() != "", "Action label cannot be empty")
        _require(self.kind in set(ActionKind), f"Invalid action kind: {self.kind!r}")
        _require(self.level in set(IntegrationLevel), f"Invalid integration level: {self.level!r}")
        _require(len(self.label) <= 80, "Action label is too long")
        _require(len(self.description) <= 400, "Action description is too long")
        names = [p.name for p in self.parameters]
        _require(len(names) == len(set(names)), f"Duplicate parameter names in action {self.id!r}")
        for permission in self.permissions:
            _require(_PERMISSION.fullmatch(permission) is not None,
                     f"Invalid permission name in action {self.id!r}")

    def validate_arguments(self, arguments: Mapping[str, Any] | None) -> dict[str, Any]:
        """Return normalized arguments or raise ``IntegrationError``."""
        provided = dict(arguments or {})
        known = {p.name for p in self.parameters}
        unknown = set(provided) - known
        _require(not unknown, f"Unknown parameters for {self.id!r}: {', '.join(sorted(unknown))}")
        required = {p.name for p in self.parameters if p.required}
        missing = required - set(provided)
        _require(not missing, f"Missing parameters for {self.id!r}: {', '.join(sorted(missing))}")
        normalized: dict[str, Any] = {}
        for parameter in self.parameters:
            if parameter.name in provided:
                normalized[parameter.name] = parameter.coerce(provided[parameter.name])
        return normalized


@dataclass(frozen=True)
class ConnectorManifest:
    """Declared integration surface of one Android app.

    A manifest is produced from documentation, an exported ``<intent-filter>``,
    an official SDK/API or a LEYRA plugin. It is *not* inferred from private
    data, and apps without a public surface never get one.
    """

    id: str
    name: str
    package_name: str
    version: str
    level: IntegrationLevel
    actions: tuple[ConnectorAction, ...] = ()
    auth: AuthMethod = AuthMethod.NONE
    publisher: str = ""
    trusted: bool = False
    notes: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.auth, AuthMethod):
            object.__setattr__(self, "auth", AuthMethod(str(self.auth)))
        _require(bool(_CONNECTOR_ID.fullmatch(self.id)), f"Invalid connector id: {self.id!r}")
        _require(bool(_PACKAGE.fullmatch(self.package_name)), f"Invalid package name: {self.package_name!r}")
        _require(bool(_SEMVER.fullmatch(self.version)), f"Invalid version: {self.version!r}")
        _require(self.name.strip() != "" and len(self.name) <= 80, "Connector name is required")
        _require(self.level in set(IntegrationLevel), f"Invalid integration level: {self.level!r}")
        _require(self.auth in set(AuthMethod), f"Invalid auth method: {self.auth!r}")
        ids = [action.id for action in self.actions]
        _require(len(ids) == len(set(ids)), f"Duplicate action ids in connector {self.id!r}")
        for action in self.actions:
            _require(action.level <= self.level,
                     f"Action {action.id!r} exceeds the declared integration level of {self.id!r}")
        launcher = [a for a in self.actions if a.kind is ActionKind.LAUNCH]
        _require(len(launcher) <= 1, "A connector can declare at most one launch action")

    @property
    def permissions(self) -> tuple[str, ...]:
        seen: list[str] = []
        for action in self.actions:
            for permission in action.permissions:
                if permission not in seen:
                    seen.append(permission)
        return tuple(seen)

    def action(self, action_id: str) -> ConnectorAction:
        for action in self.actions:
            if action.id == action_id:
                return action
        raise IntegrationError(f"Connector {self.id!r} has no action {action_id!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "packageName": self.package_name,
            "version": self.version,
            "level": int(self.level),
            "auth": self.auth.value,
            "publisher": self.publisher,
            "trusted": self.trusted,
            "notes": self.notes,
            "permissions": list(self.permissions),
            "actions": [action_to_dict(action) for action in self.actions],
        }


def action_to_dict(action: ConnectorAction) -> dict[str, Any]:
    return {
        "id": action.id,
        "label": action.label,
        "kind": action.kind.value,
        "level": int(action.level),
        "description": action.description,
        "destructive": action.destructive,
        "permissions": list(action.permissions),
        "parameters": [
            {"name": p.name, "type": p.type.value, "required": p.required, "description": p.description}
            for p in action.parameters
        ],
    }


@dataclass(frozen=True)
class DiscoveredApp:
    """Result of a PackageManager query performed by the Android bridge."""

    package_name: str
    label: str
    version_name: str = "0"
    version_code: int = 0
    installed: bool = True

    def __post_init__(self) -> None:
        _require(bool(_PACKAGE.fullmatch(self.package_name)), f"Invalid package name: {self.package_name!r}")
        _require(self.label.strip() != "", "App label is required")
        _require(isinstance(self.version_code, int) and self.version_code >= 0, "Invalid version code")


@dataclass(frozen=True)
class LinkedApp:
    """An app the user explicitly linked to LEYRA."""

    package_name: str
    label: str
    connector_id: str
    level: IntegrationLevel
    status: CapabilityStatus
    granted_permissions: tuple[str, ...] = ()
    enabled: bool = True
    linked_at: float = 0.0
    missing_permissions: tuple[str, ...] = ()
    last_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "packageName": self.package_name,
            "label": self.label,
            "connectorId": self.connector_id,
            "level": int(self.level),
            "status": self.status.value,
            "grantedPermissions": list(self.granted_permissions),
            "missingPermissions": list(self.missing_permissions),
            "enabled": self.enabled,
            "linkedAt": self.linked_at,
            "lastError": self.last_error,
        }


@dataclass(frozen=True)
class ActionStep:
    """One planned call into a linked app."""

    connector_id: str
    package_name: str
    action_id: str
    action_label: str
    arguments: dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "connectorId": self.connector_id,
            "packageName": self.package_name,
            "actionId": self.action_id,
            "actionLabel": self.action_label,
            "arguments": dict(self.arguments),
            "requiresConfirmation": self.requires_confirmation,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class IntegrationPlan:
    """An ordered, reviewable plan. Nothing here has been executed yet."""

    instruction: str
    steps: tuple[ActionStep, ...]
    notes: tuple[str, ...] = ()

    @property
    def requires_confirmation(self) -> bool:
        return any(step.requires_confirmation for step in self.steps)

    def to_dict(self) -> dict[str, Any]:
        return {
            "instruction": self.instruction,
            "steps": [step.to_dict() for step in self.steps],
            "notes": list(self.notes),
            "requiresConfirmation": self.requires_confirmation,
        }


class ExecutionStatus(str, Enum):
    OK = "ok"
    UNAVAILABLE = "unavailable"
    DENIED = "denied"
    CONFIRMATION_REQUIRED = "confirmation_required"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ExecutionResult:
    """Outcome reported back by the platform bridge."""

    status: ExecutionStatus
    connector_id: str = ""
    action_id: str = ""
    detail: str = ""
    data: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "connectorId": self.connector_id,
            "actionId": self.action_id,
            "detail": self.detail,
            "data": dict(self.data),
        }
