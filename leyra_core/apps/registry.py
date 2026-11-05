"""In-memory registry with optional JSON persistence for app integrations.

The registry only stores data the Android bridge reported (installed packages)
and manifests that were explicitly loaded. It never reads another app's storage.
"""

from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any, Iterable

from .models import (
    CapabilityStatus,
    ConnectorManifest,
    DiscoveredApp,
    IntegrationError,
    IntegrationLevel,
    LinkedApp,
)


class AppRegistry:
    """Tracks discovered apps, known connectors, links and integration history."""

    def __init__(self, persist_path: str | Path | None = None, *, clock=time.time) -> None:
        self._discovered: dict[str, DiscoveredApp] = {}
        self._manifests: dict[str, ConnectorManifest] = {}
        self._links: dict[str, LinkedApp] = {}
        self._history: list[dict[str, Any]] = []
        self._clock = clock
        self._path = Path(persist_path) if persist_path else None
        if self._path and self._path.exists():
            self._load()

    # -- discovery ---------------------------------------------------------
    def sync_discovered(self, apps: Iterable[DiscoveredApp]) -> list[DiscoveredApp]:
        """Replace the discovered set with a fresh PackageManager result."""
        fresh: dict[str, DiscoveredApp] = {}
        for app in apps:
            if not isinstance(app, DiscoveredApp):
                raise IntegrationError("Discovered entries must be DiscoveredApp instances")
            fresh[app.package_name] = app
        self._discovered = fresh
        # Links whose package disappeared are kept but flagged disabled.
        for package, link in list(self._links.items()):
            if package not in fresh and link.enabled:
                self._links[package] = _replace_link(link, enabled=False, last_error="Aplicación no instalada")
        self._persist()
        return list(fresh.values())

    def discovered(self) -> list[DiscoveredApp]:
        return sorted(self._discovered.values(), key=lambda app: app.label.lower())

    def discovered_app(self, package_name: str) -> DiscoveredApp | None:
        return self._discovered.get(package_name)

    # -- connectors --------------------------------------------------------
    def upsert_manifest(self, manifest: ConnectorManifest) -> ConnectorManifest:
        if not isinstance(manifest, ConnectorManifest):
            raise IntegrationError("manifest must be a ConnectorManifest")
        for existing in self._manifests.values():
            if existing.id == manifest.id and existing.package_name != manifest.package_name:
                raise IntegrationError(f"Connector id {manifest.id!r} is already bound to another package")
        self._manifests[manifest.package_name] = manifest
        self._persist()
        return manifest

    def manifest(self, package_name: str) -> ConnectorManifest | None:
        return self._manifests.get(package_name)

    def manifests(self) -> list[ConnectorManifest]:
        return sorted(self._manifests.values(), key=lambda m: m.name.lower())

    # -- linking -----------------------------------------------------------
    def link(self, package_name: str, *, granted_permissions: Iterable[str] = ()) -> LinkedApp:
        app = self._discovered.get(package_name)
        if app is None:
            raise IntegrationError("La aplicación no está instalada o no fue descubierta.")
        manifest = self._manifests.get(package_name)
        if manifest is None:
            raise IntegrationError("No hay un conector compatible para esta aplicación.")

        granted = tuple(sorted({str(p) for p in granted_permissions}))
        declared = set(manifest.permissions)
        unknown = set(granted) - declared
        if unknown:
            raise IntegrationError(f"El conector no declara estos permisos: {', '.join(sorted(unknown))}")

        missing = tuple(sorted(declared - set(granted)))
        if not manifest.actions:
            status = CapabilityStatus.INCOMPATIBLE
        elif missing:
            status = CapabilityStatus.PARTIAL
        elif manifest.level is IntegrationLevel.OPEN:
            status = CapabilityStatus.OPEN_ONLY
        else:
            status = CapabilityStatus.FULL

        link = LinkedApp(
            package_name=package_name,
            label=app.label,
            connector_id=manifest.id,
            level=manifest.level,
            status=status,
            granted_permissions=granted,
            enabled=True,
            linked_at=self._clock(),
            missing_permissions=missing,
        )
        self._links[package_name] = link
        self.record("link", package_name, f"Vinculada en nivel {int(manifest.level)}")
        self._persist()
        return link

    def unlink(self, package_name: str) -> LinkedApp:
        link = self._links.pop(package_name, None)
        if link is None:
            raise IntegrationError("La aplicación no está vinculada.")
        self.record("unlink", package_name, "Desvinculada por el usuario")
        self._persist()
        return _replace_link(link, enabled=False)

    def link_exists(self, package_name: str) -> bool:
        return package_name in self._links

    def linked(self) -> list[LinkedApp]:
        return sorted(self._links.values(), key=lambda link: link.label.lower())

    def linked_app(self, package_name: str) -> LinkedApp | None:
        return self._links.get(package_name)

    def set_enabled(self, package_name: str, enabled: bool) -> LinkedApp:
        link = self._require_link(package_name)
        updated = _replace_link(link, enabled=bool(enabled))
        self._links[package_name] = updated
        self.record("enable" if enabled else "disable", package_name, "Estado de integración actualizado")
        self._persist()
        return updated

    def set_permissions(self, package_name: str, granted: Iterable[str]) -> LinkedApp:
        link = self._require_link(package_name)
        manifest = self._manifests.get(package_name)
        if manifest is None:
            raise IntegrationError("No hay un conector compatible para esta aplicación.")
        granted_set = {str(p) for p in granted}
        unknown = granted_set - set(manifest.permissions)
        if unknown:
            raise IntegrationError(f"El conector no declara estos permisos: {', '.join(sorted(unknown))}")
        missing = tuple(sorted(set(manifest.permissions) - granted_set))
        status = CapabilityStatus.PARTIAL if missing else (
            CapabilityStatus.OPEN_ONLY if manifest.level is IntegrationLevel.OPEN else CapabilityStatus.FULL
        )
        updated = _replace_link(
            link,
            granted_permissions=tuple(sorted(granted_set)),
            missing_permissions=missing,
            status=status,
        )
        self._links[package_name] = updated
        self.record("permissions", package_name, "Permisos de integración actualizados")
        self._persist()
        return updated

    def mark_error(self, package_name: str, message: str) -> None:
        link = self._links.get(package_name)
        if link is None:
            return
        self._links[package_name] = _replace_link(link, last_error=str(message)[:200])
        self._persist()

    def _require_link(self, package_name: str) -> LinkedApp:
        link = self._links.get(package_name)
        if link is None:
            raise IntegrationError("La aplicación no está vinculada.")
        return link

    # -- history -----------------------------------------------------------
    def record(self, event: str, package_name: str, detail: str) -> None:
        self._history.append({
            "event": event,
            "packageName": package_name,
            "detail": str(detail)[:240],
            "at": self._clock(),
        })
        del self._history[:-200]

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(reversed(self._history[-max(0, int(limit)):]))

    # -- persistence -------------------------------------------------------
    def export_state(self) -> dict[str, Any]:
        return {
            "discovered": [
                {"packageName": a.package_name, "label": a.label,
                 "versionName": a.version_name, "versionCode": a.version_code}
                for a in self._discovered.values()
            ],
            "links": [link.to_dict() for link in self._links.values()],
            "history": self._history,
        }

    def _persist(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.export_state(), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for item in data.get("discovered", []):
            try:
                app = DiscoveredApp(
                    package_name=str(item.get("packageName", "")),
                    label=str(item.get("label", "")),
                    version_name=str(item.get("versionName", "0")),
                    version_code=int(item.get("versionCode", 0)),
                )
            except (IntegrationError, TypeError, ValueError):
                continue
            self._discovered[app.package_name] = app
        for item in data.get("links", []):
            try:
                package = str(item.get("packageName"))
                manifest = self._manifests.get(package)
                link = LinkedApp(
                    package_name=package,
                    label=str(item.get("label", package)),
                    connector_id=str(item.get("connectorId", "")),
                    level=IntegrationLevel(int(item.get("level", 1))),
                    status=CapabilityStatus(item.get("status", "partial")),
                    granted_permissions=tuple(item.get("grantedPermissions", [])),
                    enabled=bool(item.get("enabled", False)),
                    linked_at=float(item.get("linkedAt", 0)),
                    missing_permissions=tuple(item.get("missingPermissions", [])),
                    last_error=str(item.get("lastError", "")),
                )
            except (IntegrationError, TypeError, ValueError):
                continue
            self._links[link.package_name] = link
        history = data.get("history")
        if isinstance(history, list):
            self._history = [h for h in history if isinstance(h, dict)][-200:]


def _replace_link(link: LinkedApp, **changes: Any) -> LinkedApp:
    values = {
        "package_name": link.package_name,
        "label": link.label,
        "connector_id": link.connector_id,
        "level": link.level,
        "status": link.status,
        "granted_permissions": link.granted_permissions,
        "enabled": link.enabled,
        "linked_at": link.linked_at,
        "missing_permissions": link.missing_permissions,
        "last_error": link.last_error,
    }
    values.update(changes)
    return LinkedApp(**values)
