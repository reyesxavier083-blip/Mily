"""Integration tests for the LEYRA API.

Run with:
    python -m unittest discover -s backend/leyra-api/tests -v
(after ``pip install -r backend/leyra-api/requirements.txt``)
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

try:
    from fastapi.testclient import TestClient
    from app.config import Settings
    from app.main import create_app
    from app.providers import ProviderResponse, ToolCall
except ModuleNotFoundError as exc:  # pragma: no cover - dependency guard
    raise unittest.SkipTest(f"Faltan dependencias del API LEYRA: {exc}") from exc


class FakeClient:
    """Scripted provider double: no network, no credentials."""

    supports_tools = True
    supports_images = True
    supports_stream = True

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    async def complete(self, *, model, system, turns, tools=(), temperature=0.6, max_tokens=1200):
        self.calls.append({"model": model, "turns": len(turns), "tools": len(list(tools)), "system": system})
        if not self.script:
            return ProviderResponse(text="Sin más guion.")
        item = self.script.pop(0)
        if callable(item):
            return item(turns)
        return item

    async def stream(self, *, model, system, turns, temperature=0.6, max_tokens=1200):
        yield "Hola desde el proveedor de prueba."


class ApiTestCase(unittest.TestCase):
    token = ""
    env = {"OPENAI_API_KEY": "sk-test"}

    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.env_patch = patch.dict(os.environ, self.env, clear=False)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        settings = Settings(
            api_token=self.token,
            data_dir=Path(self.folder.name) / "data",
            web_dir=ROOT / "web",
            rate_limit_max=10_000,
        )
        self.app = create_app(settings)
        self.client = TestClient(self.app)

    def auth(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}


class PublicRoutesTests(ApiTestCase):
    def test_health_reports_real_configuration(self) -> None:
        payload = self.client.get("/health").json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["app"], "LEYRA IA")
        self.assertFalse(payload["androidBridge"])
        self.assertIn("gpt-4o", payload["providersConfigured"])

    def test_static_interface_is_served(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("LEYRA IA", response.text)

    def test_diagnostics_never_marks_unconfigured_modules_green(self) -> None:
        report = self.client.get("/v1/diagnostics", headers=self.auth()).json()
        modules = {module["module"]: module for module in report["modules"]}
        self.assertEqual(modules["app-integration"]["status"], "degraded")
        self.assertEqual(modules["memory"]["status"], "degraded")
        self.assertEqual(modules["vision"]["status"], "ok")

    def test_unknown_route_returns_404(self) -> None:
        self.assertEqual(self.client.get("/v1/nothing").status_code, 404)


class AuthTests(ApiTestCase):
    token = "secreto-de-prueba"

    def test_requires_token(self) -> None:
        self.assertEqual(self.client.get("/v1/tools").status_code, 401)
        self.assertEqual(self.client.get("/v1/tools", headers=self.auth()).status_code, 200)

    def test_rejects_wrong_token(self) -> None:
        response = self.client.get("/v1/tools", headers={"Authorization": "Bearer otro"})
        self.assertEqual(response.status_code, 401)

    def test_health_stays_public(self) -> None:
        self.assertEqual(self.client.get("/health").status_code, 200)


class ChatTests(ApiTestCase):
    def test_chat_without_provider_is_503(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            app = create_app(Settings(data_dir=Path(self.folder.name) / "no-key", web_dir=ROOT / "web"))
            client = TestClient(app)
            response = client.post("/v1/chat", json={"message": "hola"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("OPENAI_API_KEY", response.json()["detail"])

    def test_chat_streams_and_persists(self) -> None:
        fake = FakeClient([])
        with patch("app.main.build_client", return_value=fake):
            response = self.client.post("/v1/chat/stream", json={"message": "Hola LEYRA", "useTools": False})
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertIn("event: delta", body)
        self.assertIn("Hola desde el proveedor", body)
        self.assertIn("event: meta", body)
        conversations = self.client.get("/v1/conversations").json()["conversations"]
        self.assertEqual(len(conversations), 1)
        conversation = self.client.get(f"/v1/conversations/{conversations[0]['id']}").json()
        self.assertEqual([message["role"] for message in conversation["messages"]], ["user", "assistant"])

    def test_chat_tool_loop_executes_real_tool(self) -> None:
        fake = FakeClient([
            ProviderResponse(tool_calls=[ToolCall("call_1", "calculator.expression",
                                                  {"expression": "18/100*2450"})]),
            ProviderResponse(text="El 18 % de 2.450 es 441."),
        ])
        with patch("app.main.build_client", return_value=fake):
            response = self.client.post("/v1/chat", json={"message": "Calcula el 18% de 2450"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("441", payload["message"]["content"])
        self.assertEqual(payload["toolRuns"][0]["tool"], "calculator.expression")
        self.assertEqual(payload["toolRuns"][0]["status"], "ok")
        self.assertEqual(payload["toolRuns"][0]["output"]["value"], 441.0)
        self.assertGreaterEqual(len(fake.calls), 2)

    def test_confirmation_required_tool_is_reported_not_executed(self) -> None:
        fake = FakeClient([
            ProviderResponse(tool_calls=[ToolCall("call_1", "web.search", {"query": "leyra"})]),
            ProviderResponse(text="No hay proveedor de búsqueda configurado."),
        ])
        with patch("app.main.build_client", return_value=fake):
            response = self.client.post("/v1/chat", json={"message": "Busca LEYRA"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["toolRuns"][0]["status"], "confirmation_required")

    def test_provider_error_is_sanitized(self) -> None:
        from app.providers import ProviderError

        class Broken:
            supports_tools = True
            supports_images = True
            supports_stream = True

            async def complete(self, **kwargs):
                raise ProviderError("El proveedor limitó las solicitudes. Inténtalo en unos segundos.")

            async def stream(self, **kwargs):
                raise ProviderError("El proveedor limitó las solicitudes.")
                yield ""

        with patch("app.main.build_client", return_value=Broken()):
            response = self.client.post("/v1/chat", json={"message": "hola", "useTools": False})
        self.assertEqual(response.status_code, 502)
        self.assertIn("limitó", response.json()["detail"])

    def test_message_validation(self) -> None:
        self.assertEqual(self.client.post("/v1/chat", json={"message": "   "}).status_code, 422)

    def test_missing_conversation_is_404(self) -> None:
        with patch("app.main.build_client", return_value=FakeClient([])):
            response = self.client.post("/v1/chat", json={"message": "hola", "conversationId": "nope"})
        self.assertEqual(response.status_code, 404)


class ToolsApiTests(ApiTestCase):
    def test_tools_listing(self) -> None:
        payload = self.client.get("/v1/tools").json()
        names = {tool["name"] for tool in payload["tools"]}
        self.assertIn("calculator.expression", names)
        self.assertIn("web.search", names)

    def test_run_tool(self) -> None:
        response = self.client.post("/v1/tools/calculator.expression/run",
                                    json={"arguments": {"expression": "sqrt(2)**2"}})
        self.assertEqual(response.status_code, 200)
        self.assertAlmostEqual(response.json()["output"]["value"], 2.0)

    def test_invalid_arguments(self) -> None:
        response = self.client.post("/v1/tools/calculator.expression/run",
                                    json={"arguments": {"expression": "1/0"}})
        self.assertEqual(response.status_code, 422)

    def test_unavailable_tool_reports_503(self) -> None:
        response = self.client.post("/v1/tools/web.search/run",
                                    json={"arguments": {"query": "leyra"}, "confirmed": True})
        self.assertEqual(response.status_code, 503)
        self.assertIn("proveedor", response.json()["detail"])

    def test_external_tool_needs_confirmation(self) -> None:
        response = self.client.post("/v1/tools/web.search/run", json={"arguments": {"query": "leyra"}})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "confirmation_required")


class AppIntegrationApiTests(ApiTestCase):
    manifest = {
        "id": "whatsapp.public", "name": "WhatsApp", "packageName": "com.whatsapp",
        "version": "2.24.1", "level": 2, "auth": "none",
        "actions": [
            {"id": "open_app", "label": "Abrir WhatsApp", "kind": "launch", "level": 1},
            {"id": "share_text", "label": "Compartir texto", "kind": "share", "level": 2,
             "permissions": ["android.intent.action.SEND"],
             "parameters": [{"name": "text", "type": "text", "required": True,
                             "description": "Texto a compartir"}]},
        ],
    }

    def setup_apps(self) -> None:
        discovery = self.client.post("/v1/apps/discovery", json={"apps": [
            {"packageName": "com.whatsapp", "label": "WhatsApp", "versionName": "2.24.1", "versionCode": 1}
        ]})
        self.assertEqual(discovery.status_code, 200)
        self.assertEqual(self.client.post("/v1/apps/connectors", json={"manifest": self.manifest}).status_code, 200)

    def test_discovery_rejects_invalid_packages(self) -> None:
        response = self.client.post("/v1/apps/discovery", json={"apps": [
            {"packageName": "not a package", "label": "Bad"},
            {"packageName": "com.ok.app", "label": "Ok", "versionName": "1.0", "versionCode": 1},
        ]})
        payload = response.json()
        self.assertEqual(payload["accepted"], 1)
        self.assertEqual(len(payload["rejected"]), 1)

    def test_invalid_connector_is_rejected(self) -> None:
        bad = {"manifest": {"id": "x", "name": "X", "packageName": "com.x.y", "version": "1.0",
                            "level": 1, "actions": [{"id": "a", "label": "A", "kind": "share", "level": 3}]}}
        self.assertEqual(self.client.post("/v1/apps/connectors", json=bad).status_code, 422)

    def test_link_and_resolve(self) -> None:
        self.setup_apps()
        linked = self.client.post("/v1/apps/com.whatsapp/link",
                                  json={"grantedPermissions": ["android.intent.action.SEND"]})
        self.assertEqual(linked.status_code, 200)
        self.assertEqual(linked.json()["linked"]["status"], "full")
        plan = self.client.post("/v1/apps/resolve", json={"instruction": "Comparte el texto Hola con WhatsApp"}).json()
        self.assertEqual(plan["plan"]["steps"][0]["actionId"], "share_text")
        self.assertTrue(plan["plan"]["requiresConfirmation"])
        self.assertFalse(plan["bridge"]["available"])
        executed = self.client.post("/v1/apps/resolve",
                                    json={"instruction": "Comparte el texto Hola con WhatsApp", "confirmed": True}).json()
        self.assertEqual(executed["results"][0]["status"], "unavailable")

    def test_unavailable_bridge_is_reported(self) -> None:
        payload = self.client.get("/v1/apps").json()
        self.assertFalse(payload["bridge"]["available"])

    def test_policy_update_is_persisted(self) -> None:
        response = self.client.put("/v1/apps/policy", json={"maxLevel": 1, "blockedPackages": ["com.bad.app"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["policy"]["effectiveLevel"], 1)
        reloaded = self.app.state.services.store.get_setting("integration.policy")
        self.assertEqual(reloaded["maxLevel"], 1)
        self.assertIn("com.bad.app", self.client.get("/v1/apps").json()["policy"]["blockedPackages"])

    def test_accessibility_level_is_clamped_without_opt_in(self) -> None:
        self.client.put("/v1/apps/policy", json={"maxLevel": 5, "accessibilityOptIn": False})
        policy = self.client.get("/v1/apps").json()["policy"]
        self.assertEqual(policy["effectiveLevel"], 4)


class MemoryAndConversationTests(ApiTestCase):
    def test_memory_crud_and_export(self) -> None:
        created = self.client.post("/v1/memory", json={"text": "Prefiere español", "category": "preferencia"})
        self.assertEqual(created.status_code, 200)
        memory_id = created.json()["id"]
        self.assertEqual(self.client.get("/v1/memory").json()["count"], 1)
        self.assertEqual(len(self.client.get("/v1/memory/export").json()["memories"]), 1)
        self.assertEqual(self.client.delete(f"/v1/memory/{memory_id}").status_code, 200)
        self.assertEqual(self.client.get("/v1/memory").json()["count"], 0)

    def test_memory_flags_encryption_state_honestly(self) -> None:
        self.assertFalse(self.client.get("/v1/memory").json()["encrypted"])

    def test_conversation_management(self) -> None:
        conversation = self.client.post("/v1/conversations", json={"title": "Demo", "project": "P"}).json()
        identifier = conversation["id"]
        self.assertEqual(self.client.post(f"/v1/conversations/{identifier}/rename",
                                          json={"title": "Nuevo"}).status_code, 200)
        self.assertEqual(self.client.post(f"/v1/conversations/{identifier}/pin",
                                          json={"enabled": True}).status_code, 200)
        listed = self.client.get("/v1/conversations").json()["conversations"]
        self.assertTrue(listed[0]["pinned"])
        self.assertEqual(self.client.delete(f"/v1/conversations/{identifier}").status_code, 200)
        self.assertEqual(self.client.get(f"/v1/conversations/{identifier}").status_code, 404)

    def test_voice_settings_validation(self) -> None:
        self.assertEqual(self.client.put("/v1/voice", json={"rate": 5}).status_code, 422)
        response = self.client.put("/v1/voice", json={"rate": 1.3, "language": "es-MX"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["settings"]["rate"], 1.3)
        self.assertEqual(self.client.get("/v1/voice").json()["synthesis"], "client")

    def test_speech_preparation(self) -> None:
        payload = self.client.post("/v1/voice/prepare", json={"text": "Hola. " * 60}).json()
        self.assertGreater(payload["chunksCount"], 1)
        self.assertTrue(all(len(chunk) <= 240 for chunk in payload["chunks"]))


class FilesTests(ApiTestCase):
    def test_upload_list_download_delete(self) -> None:
        response = self.client.post("/v1/files", files={"file": ("nota.txt", b"contenido de prueba", "text/plain")})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["text"], "contenido de prueba")
        listing = self.client.get("/v1/files").json()["files"]
        self.assertEqual(len(listing), 1)
        download = self.client.get(listing[0]["downloadPath"])
        self.assertEqual(download.status_code, 200)
        self.assertEqual(self.client.delete(f"/v1/files/{payload['id']}").status_code, 200)
        self.assertEqual(self.client.get("/v1/files").json()["files"], [])

    def test_rejects_dangerous_names(self) -> None:
        response = self.client.post("/v1/files", files={"file": ("../../etc/passwd", b"x", "text/plain")})
        self.assertEqual(response.status_code, 200)
        stored = self.client.get("/v1/files").json()["files"][0]
        self.assertNotIn("/", stored["name"])
        self.assertNotIn("..", stored["name"])
        self.assertEqual(stored["name"], "passwd")


class ModelApiTests(ApiTestCase):
    def test_models_mark_configuration(self) -> None:
        payload = self.client.get("/v1/models").json()
        openai = next(provider for provider in payload["providers"] if provider["id"] == "openai")
        anthropic = next(provider for provider in payload["providers"] if provider["id"] == "anthropic")
        self.assertTrue(openai["configured"])
        self.assertFalse(anthropic["configured"])
        model_ids = {model["id"]: model for model in payload["models"]}
        self.assertTrue(model_ids["gpt-4o"]["configured"])
        self.assertFalse(model_ids["claude-3-5-sonnet-latest"]["configured"])
        self.assertNotIn("sk-test", str(payload))


if __name__ == "__main__":
    unittest.main()
