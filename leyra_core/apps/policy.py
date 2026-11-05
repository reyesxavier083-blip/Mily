"""Security policy for app-to-app integration.

Android isolates applications: without a public interface (Intent, deep link,
SDK, plugin, or a user-granted accessibility service) there is nothing to
integrate. This policy encodes the hard limits LEYRA enforces on top of that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .models import IntegrationError, IntegrationLevel


@dataclass
class IntegrationPolicy:
    """User-and-product level limits applied before any action is planned.

    Defaults are deliberately conservative: interoperability is allowed, API and
    plugin integrations must be enabled explicitly, and accessibility-based
    integration is off until the user turns it on in settings.
    """

    max_level: IntegrationLevel = IntegrationLevel.INTEROP
    accessibility_opt_in: bool = False
    blocked_packages: set[str] = field(default_factory=set)
    require_confirmation_for: frozenset[str] = frozenset({"share", "intent", "content_provider", "accessibility"})
    max_steps_per_plan: int = 8
    max_file_megabytes: int = 25

    def effective_level(self) -> IntegrationLevel:
        """Highest level the current settings permit."""
        if self.max_level is IntegrationLevel.ACCESSIBILITY and not self.accessibility_opt_in:
            # Never report level 5 as available without the explicit opt-in.
            return IntegrationLevel.PLUGIN
        return self.max_level

    def check_level(self, level: IntegrationLevel) -> None:
        if level > self.effective_level():
            raise IntegrationError(
                f"Integration level {int(level)} is disabled by the current policy "
                f"(maximum {int(self.effective_level())})."
            )

    def check_package(self, package_name: str) -> None:
        if package_name in self.blocked_packages:
            raise IntegrationError(f"Package {package_name!r} is blocked by policy.")

    def needs_confirmation(self, kind: str, *, destructive: bool) -> bool:
        return destructive or kind in self.require_confirmation_for

    def update(
        self,
        *,
        max_level: int | IntegrationLevel | None = None,
        accessibility_opt_in: bool | None = None,
        blocked_packages: Iterable[str] | None = None,
        require_confirmation_for: Iterable[str] | None = None,
    ) -> "IntegrationPolicy":
        """Return a new policy; validation happens before anything changes."""
        level = self.max_level
        if max_level is not None:
            try:
                level = IntegrationLevel(int(max_level))
            except (ValueError, TypeError) as exc:
                raise IntegrationError("max_level must be 1..5") from exc
        if accessibility_opt_in is not None and type(accessibility_opt_in) is not bool:
            raise IntegrationError("accessibility_opt_in must be a boolean")
        packages = set(self.blocked_packages)
        if blocked_packages is not None:
            packages = {str(item).strip() for item in blocked_packages if str(item).strip()}
            for package in packages:
                if not package.count(".") or " " in package:
                    raise IntegrationError(f"Invalid blocked package name: {package!r}")
        kinds = self.require_confirmation_for
        if require_confirmation_for is not None:
            kinds = frozenset(str(item) for item in require_confirmation_for)
        return IntegrationPolicy(
            max_level=level,
            accessibility_opt_in=self.accessibility_opt_in if accessibility_opt_in is None else accessibility_opt_in,
            blocked_packages=packages,
            require_confirmation_for=kinds,
            max_steps_per_plan=self.max_steps_per_plan,
            max_file_megabytes=self.max_file_megabytes,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "maxLevel": int(self.max_level),
            "effectiveLevel": int(self.effective_level()),
            "accessibilityOptIn": self.accessibility_opt_in,
            "blockedPackages": sorted(self.blocked_packages),
            "requireConfirmationFor": sorted(self.require_confirmation_for),
            "maxStepsPerPlan": self.max_steps_per_plan,
            "maxFileMegabytes": self.max_file_megabytes,
        }
