"""Wires the LEYRA engines together for one API process."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Any

from leyra_core.apps import AppIntegrationEngine, AppRegistry, IntegrationPolicy
from leyra_core.diagnostics import DiagnosticsHub, Health, ModuleHealth
from leyra_core.models import ModelRouter
from leyra_core.storage import Store
from leyra_core.tools import ToolRegistry, build_default_registry
from leyra_core.voice import VoiceError, VoiceSettings, load_settings

from .config import Settings


@dataclass
class Services:
    settings: Settings
    store: Store
    tools: ToolRegistry
    router: ModelRouter
    engine: AppIntegrationEngine
    hub: DiagnosticsHub
    uploads: Path

    def voice_settings(self) -> VoiceSettings:
        return load_settings(self.store)

    def save_voice_settings(self, settings: VoiceSettings) -> VoiceSettings:
        self.store.set_setting("voice", settings.to_dict())
        return settings

    def diagnostics(self) -> dict[str, Any]:
        return self.hub.run()


def build_services(settings: Settings) -> Services:
    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    uploads = data_dir / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)

    store = Store(data_dir / "leyra.sqlite3")
    tools = build_default_registry()
    router = ModelRouter(env=None)
    registry = AppRegistry(persist_path=data_dir / "app-integrations.json")
    stored_policy = store.get_setting("integration.policy", None)
    policy = IntegrationPolicy()
    if isinstance(stored_policy, dict):
        try:
            policy = policy.update(
                max_level=stored_policy.get("maxLevel"),
                accessibility_opt_in=stored_policy.get("accessibilityOptIn"),
                blocked_packages=stored_policy.get("blockedPackages"),
                require_confirmation_for=stored_policy.get("requireConfirmationFor"),
            )
        except ValueError:
            policy = IntegrationPolicy()
    engine = AppIntegrationEngine(registry=registry, policy=policy)

    hub = DiagnosticsHub()
    hub.register_engine("core", _CoreHealth(settings.version))
    hub.register_engine("ai-engine", router)
    hub.register_engine("tools", tools)
    hub.register_engine("app-integration", engine)

    def storage_check() -> ModuleHealth:
        try:
            stats = store.stats()
        except Exception:
            return ModuleHealth("storage", Health.ERROR, "La base de datos no responde.")
        return ModuleHealth(
            "storage", Health.OK,
            f"{stats['conversations']} conversaciones, {stats['memories']} recuerdos, "
            f"{stats['sizeBytes'] // 1024} KB en disco.",
            stats,
        )

    def memory_check() -> ModuleHealth:
        stats = store.stats()
        return ModuleHealth(
            "memory", Health.DEGRADED,
            "Memoria local en SQLite con procedencia y deduplicación. El cifrado en reposo "
            "todavía no está implementado: protege el volumen de datos del servidor.",
            {"memories": stats["memories"], "encrypted": False},
        )

    def voice_check() -> ModuleHealth:
        try:
            settings_now = load_settings(store)
        except Exception:
            return ModuleHealth("voice", Health.ERROR, "La configuración de voz no pudo validarse.")
        return ModuleHealth(
            "voice", Health.OK,
            f"Configuración válida para {settings_now.language} · velocidad {settings_now.rate}×. "
            "La síntesis se ejecuta en el cliente (Web Speech o TTS de Android).",
            settings_now.to_dict(),
        )

    def vision_check() -> ModuleHealth:
        configured = [m for m in router.configured_models() if any(c.value == "vision" for c in m.capabilities)]
        return ModuleHealth(
            "vision", Health.OK if configured else Health.UNAVAILABLE,
            "Hay modelos con visión configurados." if configured
            else "Ningún proveedor con visión está configurado en el servidor.",
            {"models": [m.id for m in configured]},
        )

    def web_check() -> ModuleHealth:
        index = Path(settings.web_dir) / "index.html"
        return ModuleHealth(
            "web",
            Health.OK if index.exists() else Health.ERROR,
            "Interfaz web servida desde este proceso." if index.exists()
            else f"No se encontró la interfaz en {settings.web_dir}.",
            {"path": str(settings.web_dir), "index": index.exists()},
        )

    def disk_check() -> ModuleHealth:
        usage = shutil.disk_usage(data_dir)
        free_mb = usage.free // (1024 * 1024)
        return ModuleHealth(
            "disk",
            Health.OK if free_mb > 200 else Health.DEGRADED,
            f"{free_mb} MB libres para datos y archivos.",
            {"freeMegabytes": free_mb},
        )

    hub.register("storage", storage_check)
    hub.register("memory", memory_check)
    hub.register("voice", voice_check)
    hub.register("vision", vision_check)
    hub.register("web", web_check)
    hub.register("disk", disk_check)

    return Services(settings, store, tools, router, engine, hub, uploads)


class _CoreHealth:
    def __init__(self, version: str) -> None:
        self._version = version

    def health(self) -> dict[str, Any]:
        return {
            "module": "core",
            "status": "ok",
            "detail": f"LEYRA CORE {self._version} activo.",
            "version": self._version,
        }
