"""Tests for the LEYRA ANDROID APP INTEGRATION ENGINE."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from leyra_core.apps import (
    ActionKind,
    AppIntegrationEngine,
    AppRegistry,
    CapabilityStatus,
    ConnectorAction,
    ConnectorManifest,
    DiscoveredApp,
    ExecutionResult,
    ExecutionStatus,
    IntegrationError,
    IntegrationLevel,
    IntegrationPolicy,
)
from leyra_core.apps.models import ActionParameter, ParamType


def whatsapp() -> ConnectorManifest:
    return ConnectorManifest(
        id="whatsapp.public",
        name="WhatsApp",
        package_name="com.whatsapp",
        version="2.24.1",
        level=IntegrationLevel.INTEROP,
        actions=(
            ConnectorAction(id="open_app", label="Abrir WhatsApp", kind=ActionKind.LAUNCH,
                            level=IntegrationLevel.OPEN),
            ConnectorAction(
                id="share_text", label="Compartir texto", kind=ActionKind.SHARE,
                level=IntegrationLevel.INTEROP, permissions=("android.intent.action.SEND",),
                parameters=(ActionParameter("text", ParamType.TEXT, "Texto a compartir"),),
            ),
            ConnectorAction(
                id="open_link", label="Abrir enlace", kind=ActionKind.APP_LINK,
                level=IntegrationLevel.INTEROP,
                parameters=(ActionParameter("url", ParamType.URL, "Enlace"),),
            ),
        ),
    )


class FakeBridge:
    name = "fake-android"

    def __init__(self, available: bool = True, status: ExecutionStatus = ExecutionStatus.OK) -> None:
        self._available = available
        self._status = status
        self.calls: list[tuple[str, str, dict]] = []

    def available(self) -> bool:
        return self._available

    def dispatch(self, step) -> ExecutionResult:
        self.calls.append((step.package_name, step.action_id, dict(step.arguments)))
        return ExecutionResult(self._status, step.connector_id, step.action_id, "despachado")


def build_engine(**kwargs) -> AppIntegrationEngine:
    registry = AppRegistry()
    bridge = kwargs.pop("bridge", None)
    engine = AppIntegrationEngine(registry=registry, bridge=bridge, **kwargs)
    engine.sync_discovery([
        DiscoveredApp("com.whatsapp", "WhatsApp", "2.24.1", 24010),
        DiscoveredApp("com.google.android.gm", "Gmail", "2024.1", 900),
    ])
    engine.register_connector(whatsapp())
    return engine


class ManifestTests(unittest.TestCase):
    def test_rejects_invalid_package_and_version(self) -> None:
        with self.assertRaises(IntegrationError):
            ConnectorManifest(id="x.y", name="X", package_name="not a package", version="1.0",
                              level=IntegrationLevel.OPEN)
        with self.assertRaises(IntegrationError):
            ConnectorManifest(id="x.y", name="X", package_name="com.x.y", version="beta!",
                              level=IntegrationLevel.OPEN)

    def test_action_cannot_exceed_manifest_level(self) -> None:
        with self.assertRaises(IntegrationError):
            ConnectorManifest(
                id="x.y", name="X", package_name="com.x.y", version="1.0",
                level=IntegrationLevel.OPEN,
                actions=(ConnectorAction(id="share", label="Compartir", kind=ActionKind.SHARE,
                                         level=IntegrationLevel.INTEROP),),
            )

    def test_duplicate_action_ids_rejected(self) -> None:
        action = ConnectorAction(id="open", label="Abrir", kind=ActionKind.LAUNCH, level=IntegrationLevel.OPEN)
        with self.assertRaises(IntegrationError):
            ConnectorManifest(id="x.y", name="X", package_name="com.x.y", version="1.0",
                              level=IntegrationLevel.OPEN, actions=(action, action))

    def test_argument_validation(self) -> None:
        action = whatsapp().action("share_text")
        self.assertEqual(action.validate_arguments({"text": "hola"}), {"text": "hola"})
        with self.assertRaises(IntegrationError):
            action.validate_arguments({})
        with self.assertRaises(IntegrationError):
            action.validate_arguments({"text": "hola", "extra": 1})
        with self.assertRaises(IntegrationError):
            whatsapp().action("open_link").validate_arguments({"url": "javascript:alert(1)"})

    def test_manifest_serialization_is_json_safe(self) -> None:
        payload = whatsapp().to_dict()
        json.dumps(payload)
        self.assertEqual(payload["level"], 2)
        self.assertIn("android.intent.action.SEND", payload["permissions"])


class PolicyTests(unittest.TestCase):
    def test_accessibility_level_requires_opt_in(self) -> None:
        policy = IntegrationPolicy(max_level=IntegrationLevel.ACCESSIBILITY)
        self.assertEqual(policy.effective_level(), IntegrationLevel.PLUGIN)
        opted_in = policy.update(accessibility_opt_in=True)
        self.assertEqual(opted_in.effective_level(), IntegrationLevel.ACCESSIBILITY)

    def test_check_level_rejects_disabled_levels(self) -> None:
        policy = IntegrationPolicy(max_level=IntegrationLevel.INTEROP)
        policy.check_level(IntegrationLevel.OPEN)
        with self.assertRaises(IntegrationError):
            policy.check_level(IntegrationLevel.PLUGIN)

    def test_confirmation_matrix(self) -> None:
        policy = IntegrationPolicy()
        self.assertTrue(policy.needs_confirmation("share", destructive=False))
        self.assertFalse(policy.needs_confirmation("launch", destructive=False))
        self.assertTrue(policy.needs_confirmation("launch", destructive=True))

    def test_invalid_updates_rejected(self) -> None:
        policy = IntegrationPolicy()
        with self.assertRaises(IntegrationError):
            policy.update(max_level=9)
        with self.assertRaises(IntegrationError):
            policy.update(accessibility_opt_in="yes")


class LinkTests(unittest.TestCase):
    def test_linking_unknown_package_fails(self) -> None:
        engine = build_engine()
        with self.assertRaises(IntegrationError):
            engine.link("com.unknown.app")

    def test_link_without_connector_creates_open_only_connector(self) -> None:
        engine = build_engine()
        link = engine.link("com.google.android.gm")
        self.assertEqual(link["status"], "open_only")
        self.assertEqual(link["level"], 1)

    def test_missing_permissions_make_integration_partial(self) -> None:
        engine = build_engine()
        link = engine.link("com.whatsapp", granted_permissions=[])
        self.assertEqual(link["status"], "partial")
        self.assertEqual(link["missingPermissions"], ["android.intent.action.SEND"])

    def test_unknown_permission_rejected(self) -> None:
        engine = build_engine()
        with self.assertRaises(IntegrationError):
            engine.link("com.whatsapp", granted_permissions=["android.permission.READ_SMS"])

    def test_permission_revocation_degrades_status(self) -> None:
        engine = build_engine()
        engine.link("com.whatsapp", granted_permissions=["android.intent.action.SEND"])
        updated = engine.set_permissions("com.whatsapp", [])
        self.assertEqual(updated["status"], "partial")
        with self.assertRaises(IntegrationError):
            engine.set_permissions("com.whatsapp", ["not.declared"])

    def test_unlink_and_history(self) -> None:
        engine = build_engine()
        engine.link("com.whatsapp", granted_permissions=["android.intent.action.SEND"])
        engine.unlink("com.whatsapp")
        self.assertIsNone(engine.registry.linked_app("com.whatsapp"))
        events = [entry["event"] for entry in engine.registry.history()]
        self.assertIn("link", events)
        self.assertIn("unlink", events)

    def test_blocked_package_cannot_be_linked(self) -> None:
        policy = IntegrationPolicy(blocked_packages={"com.whatsapp"})
        engine = build_engine(policy=policy)
        with self.assertRaises(IntegrationError):
            engine.link("com.whatsapp")


class CatalogTests(unittest.TestCase):
    def test_catalog_reports_real_compatibility(self) -> None:
        engine = build_engine()
        catalog = {entry["packageName"]: entry for entry in engine.catalog()}
        self.assertEqual(catalog["com.whatsapp"]["status"], "full")
        self.assertEqual(catalog["com.google.android.gm"]["status"], "open_only")
        self.assertIn("note", catalog["com.whatsapp"])

    def test_policy_downgrades_higher_level_connector(self) -> None:
        policy = IntegrationPolicy(max_level=IntegrationLevel.OPEN)
        engine = build_engine(policy=policy)
        catalog = {entry["packageName"]: entry for entry in engine.catalog()}
        self.assertEqual(catalog["com.whatsapp"]["status"], "open_only")
        self.assertIn("Requiere nivel 2", catalog["com.whatsapp"]["note"])

    def test_capability_search(self) -> None:
        engine = build_engine()
        results = engine.find_capabilities("compartir texto")
        self.assertTrue(results)
        self.assertEqual(results[0]["action"], "share_text")
        with self.assertRaises(IntegrationError):
            engine.find_capabilities("  ")


class ResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = build_engine()
        self.engine.link("com.whatsapp", granted_permissions=["android.intent.action.SEND"])

    def test_open_instruction(self) -> None:
        plan = self.engine.resolve("Abre WhatsApp")
        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].action_id, "open_app")
        self.assertFalse(plan.requires_confirmation)

    def test_share_keeps_original_text_and_needs_confirmation(self) -> None:
        plan = self.engine.resolve("Comparte el texto Hola Equipo, informe listo con WhatsApp")
        self.assertEqual(plan.steps[0].arguments["text"], "Hola Equipo, informe listo")
        self.assertTrue(plan.requires_confirmation)

    def test_share_without_text_asks_for_it(self) -> None:
        with self.assertRaises(IntegrationError):
            self.engine.resolve("comparte el texto con WhatsApp")

    def test_open_deep_link(self) -> None:
        plan = self.engine.resolve("abre https://leyra.app en WhatsApp")
        self.assertEqual(plan.steps[0].arguments["url"], "https://leyra.app")

    def test_unlinked_app_cannot_be_used(self) -> None:
        engine = build_engine()
        with self.assertRaises(IntegrationError):
            engine.resolve("Abre WhatsApp")

    def test_unknown_app_message(self) -> None:
        with self.assertRaises(IntegrationError):
            self.engine.resolve("abre BancoImaginario")

    def test_capabilities_and_linked_listing(self) -> None:
        scope = self.engine.describe("¿Qué aplicaciones pueden compartir texto?")
        self.assertTrue(scope["capabilities"])
        listing = self.engine.describe("muéstrame las aplicaciones vinculadas")
        self.assertEqual(len(listing["linked"]), 1)

    def test_unrecognized_instruction(self) -> None:
        with self.assertRaises(IntegrationError):
            self.engine.resolve("hazme un café")


class ExecutionTests(unittest.TestCase):
    def test_confirmation_required_blocks_execution(self) -> None:
        bridge = FakeBridge()
        engine = build_engine(bridge=bridge)
        engine.link("com.whatsapp", granted_permissions=["android.intent.action.SEND"])
        plan = engine.resolve("Comparte el texto Hola con WhatsApp")
        results = engine.execute(plan, confirmed=False)
        self.assertEqual(results[0].status, ExecutionStatus.CONFIRMATION_REQUIRED)
        self.assertEqual(bridge.calls, [])

    def test_confirmed_execution_dispatches(self) -> None:
        bridge = FakeBridge()
        engine = build_engine(bridge=bridge)
        engine.link("com.whatsapp", granted_permissions=["android.intent.action.SEND"])
        plan = engine.resolve("Comparte el texto Hola con WhatsApp")
        results = engine.execute(plan, confirmed=True)
        self.assertEqual(results[0].status, ExecutionStatus.OK)
        self.assertEqual(bridge.calls[0][:2], ("com.whatsapp", "share_text"))

    def test_without_bridge_reports_unavailable(self) -> None:
        engine = build_engine()
        engine.link("com.whatsapp", granted_permissions=["android.intent.action.SEND"])
        plan = engine.resolve("Abre WhatsApp")
        results = engine.execute(plan, confirmed=True)
        self.assertEqual(results[0].status, ExecutionStatus.UNAVAILABLE)
        self.assertIn("Android", results[0].detail)

    def test_disabled_link_denies_execution(self) -> None:
        bridge = FakeBridge()
        engine = build_engine(bridge=bridge)
        engine.link("com.whatsapp", granted_permissions=["android.intent.action.SEND"])
        plan = engine.resolve("Abre WhatsApp")
        engine.set_enabled("com.whatsapp", False)
        results = engine.execute(plan, confirmed=True)
        self.assertEqual(results[0].status, ExecutionStatus.DENIED)
        self.assertEqual(bridge.calls, [])

    def test_failed_dispatch_stops_plan(self) -> None:
        bridge = FakeBridge(status=ExecutionStatus.FAILED)
        engine = build_engine(bridge=bridge)
        engine.link("com.whatsapp", granted_permissions=["android.intent.action.SEND"])
        results = engine.execute(engine.resolve("Abre WhatsApp"), confirmed=True)
        self.assertEqual(results[0].status, ExecutionStatus.FAILED)
        self.assertEqual(engine.registry.linked_app("com.whatsapp").last_error, "despachado")


class RegistryPersistenceTests(unittest.TestCase):
    def test_state_survives_reload(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "apps.json"
            engine = AppIntegrationEngine(registry=AppRegistry(persist_path=path))
            engine.sync_discovery([DiscoveredApp("com.whatsapp", "WhatsApp", "2.24.1", 1)])
            engine.register_connector(whatsapp())
            engine.link("com.whatsapp", granted_permissions=["android.intent.action.SEND"])
            engine.registry.set_permissions("com.whatsapp", ["android.intent.action.SEND"])

            reloaded = AppIntegrationEngine(registry=AppRegistry(persist_path=path))
            link = reloaded.registry.linked_app("com.whatsapp")
            self.assertIsNotNone(link)
            self.assertEqual(link.status, CapabilityStatus.FULL)
            self.assertEqual(reloaded.registry.discovered_app("com.whatsapp").label, "WhatsApp")

    def test_connectors_and_plans_survive_reload(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "apps.json"
            engine = AppIntegrationEngine(registry=AppRegistry(persist_path=path))
            engine.sync_discovery([DiscoveredApp("com.whatsapp", "WhatsApp", "2.24.1", 1)])
            engine.register_connector(whatsapp())
            engine.link("com.whatsapp", granted_permissions=["android.intent.action.SEND"])

            reloaded = AppIntegrationEngine(registry=AppRegistry(persist_path=path))
            self.assertEqual([manifest.id for manifest in reloaded.registry.manifests()], ["whatsapp.public"])
            plan = reloaded.resolve("Abre WhatsApp")
            self.assertEqual(plan.steps[0].package_name, "com.whatsapp")

    def test_uninstalled_app_disables_link(self) -> None:
        engine = build_engine()
        engine.link("com.whatsapp", granted_permissions=["android.intent.action.SEND"])
        engine.sync_discovery([DiscoveredApp("com.google.android.gm", "Gmail", "2024.1", 1)])
        link = engine.registry.linked_app("com.whatsapp")
        self.assertFalse(link.enabled)
        self.assertIn("no instalada", link.last_error)


class HealthTests(unittest.TestCase):
    def test_health_reports_bridge_state(self) -> None:
        engine = build_engine()
        health = engine.health()
        self.assertEqual(health["status"], "degraded")
        self.assertFalse(health["bridge"]["available"])
        healthy = build_engine(bridge=FakeBridge()).health()
        self.assertEqual(healthy["status"], "ok")
        self.assertEqual(healthy["linked"], 0)


if __name__ == "__main__":
    unittest.main()
