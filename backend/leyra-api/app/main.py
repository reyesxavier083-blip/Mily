"""LEYRA API.

Serves the LEYRA web interface and the JSON API used by web and Android:
chat (with real tool execution), multimodel routing, tools, memory,
conversations, Android app integration, voice settings and diagnostics.

Nothing here pretends to work: an unconfigured provider, a missing dependency or
an absent Android bridge is reported as such.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import asyncio
import hmac
import json
from pathlib import Path
import re
import time
from typing import Any, AsyncIterator, Iterable
import uuid

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from leyra_core.apps import ConnectorAction, ConnectorManifest, DiscoveredApp, IntegrationError, IntegrationLevel
from leyra_core.models import Capability, RouterError, TaskKind
from leyra_core.tools import ToolError, ToolStatus
from leyra_core.voice import STYLES, LANGUAGES, VoiceError, VoiceSettings, chunk_text, expressive_text

from .config import RateLimiter, Settings
from .providers import ProviderError, Turn, build_client, parse_data_url
from .state import Services, build_services

APP_TITLE = "LEYRA IA"
MAX_TOOL_ROUNDS = 3
MAX_IMAGES = 4


def tool_alias(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "__", name)[:64]


SYSTEM_PROMPT = """Eres LEYRA IA, una asistente de inteligencia artificial avanzada y multimodal.

Reglas:
- Responde en el idioma del usuario (por defecto, español claro y natural).
- Usa Markdown: títulos breves, listas, tablas y bloques de código con lenguaje.
- Muestra fórmulas matemáticas con notación LaTeX entre $...$ o $$...$$ cuando aporte claridad.
- Si usas una herramienta, explica el resultado real que devolvió. Nunca inventes ejecuciones, datos, fuentes ni cifras.
- Cuando una herramienta no esté disponible o falte una credencial, dilo con precisión y ofrece la alternativa posible.
- Cita las fuentes solo cuando provengan de una búsqueda real; si no hay fuentes, no las inventes.
- Sobre integraciones Android: puedes abrir apps, compartir contenido y usar interfaces públicas autorizadas. No puedes leer datos privados de otras aplicaciones ni eludir permisos de Android; si te lo piden, explícalo y propón la vía permitida.
- Las acciones con efectos externos requieren confirmación explícita del usuario.
- Sé concisa, útil y honesta sobre tus límites.
"""


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    conversationId: str | None = Field(default=None, max_length=64)
    model: str | None = Field(default=None, max_length=120)
    useTools: bool = True
    reasoning: bool = False
    images: list[str] = Field(default_factory=list, max_length=MAX_IMAGES)
    confirmedTools: bool = False

    @field_validator("message")
    @classmethod
    def _clean(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("El mensaje está vacío.")
        return text


class ConversationRequest(BaseModel):
    title: str = Field(default="Nueva conversación", max_length=120)
    project: str | None = Field(default=None, max_length=80)


class RenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class MemoryRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    category: str = Field(default="general", max_length=60)
    provenance: str = Field(default="user", max_length=60)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class ToolRunRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = False


class DiscoveryRequest(BaseModel):
    apps: list[dict[str, Any]] = Field(default_factory=list, max_length=2000)


class ConnectorRequest(BaseModel):
    manifest: dict[str, Any]


class LinkRequest(BaseModel):
    grantedPermissions: list[str] = Field(default_factory=list)


class PermissionsRequest(BaseModel):
    grantedPermissions: list[str] = Field(default_factory=list)


class EnabledRequest(BaseModel):
    enabled: bool


class PolicyRequest(BaseModel):
    maxLevel: int | None = Field(default=None, ge=1, le=5)
    accessibilityOptIn: bool | None = None
    blockedPackages: list[str] | None = None
    requireConfirmationFor: list[str] | None = None


class ResolveRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=500)
    confirmed: bool = False


class VoiceRequest(BaseModel):
    voiceName: str | None = Field(default=None, max_length=40)
    voiceId: str | None = Field(default=None, max_length=120)
    language: str | None = None
    rate: float | None = Field(default=None, ge=0.5, le=2.0)
    pitch: float | None = Field(default=None, ge=0.0, le=2.0)
    volume: float | None = Field(default=None, ge=0.0, le=1.0)
    style: str | None = None
    expressivePauses: bool | None = None
    autoSpeak: bool | None = None
    bargeIn: bool | None = None


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=12000)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings.from_env()
    services = build_services(config)
    limiter = RateLimiter(window=config.rate_limit_window, maximum=config.rate_limit_max)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        services.store.close()

    app = FastAPI(title=APP_TITLE, version=config.version, docs_url="/api/docs",
                  openapi_url="/api/openapi.json", lifespan=lifespan)
    app.state.services = services
    app.state.config = config

    if config.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(config.allowed_origins),
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "Accept"],
            max_age=600,
        )

    @app.middleware("http")
    async def guard(request: Request, call_next):
        path = request.url.path
        origin = request.headers.get("origin", "")
        host = request.headers.get("host", "")
        same_origin = bool(origin) and origin.split("://")[-1].rstrip("/") == host.rstrip("/")

        if origin and origin.rstrip("/") not in config.allowed_origins and not same_origin:
            return JSONResponse({"detail": "Origen no permitido."}, status_code=403)
        if request.method == "OPTIONS":
            return JSONResponse({}, status_code=204)

        if path.startswith("/v1/"):
            if config.auth_required:
                supplied = request.headers.get("authorization", "")
                token = supplied[7:].strip() if supplied.lower().startswith("bearer ") else ""
                if not hmac.compare_digest(token.encode("utf-8"), config.api_token.encode("utf-8")):
                    return JSONResponse({"detail": "No autorizado."}, status_code=401)
            client_ip = request.client.host if request.client else "unknown"
            if not limiter.allow(client_ip, now=time.time()):
                return JSONResponse({"detail": "Demasiadas solicitudes. Inténtalo en un minuto."}, status_code=429)
            length = request.headers.get("content-length")
            if length and length.isdigit() and int(length) > config.max_body_bytes:
                return JSONResponse({"detail": "La solicitud es demasiado grande."}, status_code=413)

        response = await call_next(request)
        if path.startswith(("/styles.css", "/app.js", "/index.html")) or path == "/":
            response.headers["Cache-Control"] = "no-store"
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    def svc(request: Request) -> Services:
        return request.app.state.services

    # -- health ------------------------------------------------------------
    @app.get("/health")
    def health() -> dict[str, Any]:
        configured = [model.id for model in services.router.configured_models()]
        return {
            "ok": True,
            "app": APP_TITLE,
            "version": config.version,
            "environment": "web",
            "authRequired": config.auth_required,
            "providersConfigured": configured,
            "model": configured[0] if configured else "",
            "androidBridge": services.engine.bridge.available(),
        }

    @app.get("/v1/diagnostics")
    def diagnostics(request: Request) -> dict[str, Any]:
        report = svc(request).diagnostics()
        report["app"] = APP_TITLE
        report["version"] = config.version
        return report

    # -- models ------------------------------------------------------------
    @app.get("/v1/models")
    def models() -> dict[str, Any]:
        configured = {m.id for m in services.router.configured_models()}
        return {
            "models": [
                {**model.to_dict(), "configured": model.id in configured}
                for model in services.router.registry.all()
            ],
            "providers": [provider.to_dict(services.router.env()) for provider in services.router.providers.values()],
            "default": config.default_model or "",
        }

    # -- conversations -----------------------------------------------------
    @app.get("/v1/conversations")
    def list_conversations(request: Request, q: str = "", limit: int = 50) -> dict[str, Any]:
        return {"conversations": svc(request).store.list_conversations(limit=limit, query=q)}

    @app.post("/v1/conversations")
    def create_conversation(request: Request, payload: ConversationRequest) -> dict[str, Any]:
        return svc(request).store.create_conversation(payload.title, payload.project)

    @app.get("/v1/conversations/{conversation_id}")
    def get_conversation(request: Request, conversation_id: str) -> dict[str, Any]:
        conversation = svc(request).store.get_conversation(conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversación no encontrada.")
        return conversation

    @app.delete("/v1/conversations/{conversation_id}")
    def delete_conversation(request: Request, conversation_id: str) -> dict[str, Any]:
        if not svc(request).store.delete_conversation(conversation_id):
            raise HTTPException(status_code=404, detail="Conversación no encontrada.")
        return {"deleted": True}

    @app.post("/v1/conversations/{conversation_id}/rename")
    def rename_conversation(request: Request, conversation_id: str, payload: RenameRequest) -> dict[str, Any]:
        if not svc(request).store.rename_conversation(conversation_id, payload.title):
            raise HTTPException(status_code=404, detail="Conversación no encontrada.")
        return {"renamed": True}

    @app.post("/v1/conversations/{conversation_id}/pin")
    def pin_conversation(request: Request, conversation_id: str, payload: EnabledRequest) -> dict[str, Any]:
        if not svc(request).store.set_pinned(conversation_id, payload.enabled):
            raise HTTPException(status_code=404, detail="Conversación no encontrada.")
        return {"pinned": payload.enabled}

    # -- memory ------------------------------------------------------------
    @app.get("/v1/memory")
    def list_memory(request: Request, q: str = "", limit: int = 100) -> dict[str, Any]:
        items = svc(request).store.list_memories(limit=limit, query=q)
        return {"memories": items, "count": len(items), "encrypted": False}

    @app.post("/v1/memory")
    def add_memory(request: Request, payload: MemoryRequest) -> dict[str, Any]:
        try:
            return svc(request).store.upsert_memory(payload.text, category=payload.category,
                                                    provenance=payload.provenance, confidence=payload.confidence)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.delete("/v1/memory/{memory_id}")
    def delete_memory(request: Request, memory_id: str) -> dict[str, Any]:
        if not svc(request).store.delete_memory(memory_id):
            raise HTTPException(status_code=404, detail="Recuerdo no encontrado.")
        return {"deleted": True}

    @app.get("/v1/memory/export")
    def export_memory(request: Request) -> dict[str, Any]:
        return {"exportedAt": time.time(), "memories": svc(request).store.export_memories()}

    # -- voice -------------------------------------------------------------
    @app.get("/v1/voice")
    def get_voice(request: Request) -> dict[str, Any]:
        settings_now = svc(request).voice_settings()
        return {
            "settings": settings_now.to_dict(),
            "languages": sorted(LANGUAGES),
            "styles": sorted(STYLES),
            "synthesis": "client",
        }

    @app.put("/v1/voice")
    def put_voice(request: Request, payload: VoiceRequest) -> dict[str, Any]:
        current = svc(request).voice_settings()
        merged = current.to_dict()
        for key, value in payload.model_dump(exclude_none=True).items():
            merged[key] = value
        try:
            updated = VoiceSettings.from_dict(merged)
        except (VoiceError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        svc(request).save_voice_settings(updated)
        return {"settings": updated.to_dict()}

    @app.post("/v1/voice/prepare")
    def prepare_speech(request: Request, payload: SpeakRequest) -> dict[str, Any]:
        settings_now = svc(request).voice_settings()
        text = expressive_text(payload.text, settings_now)
        chunks = chunk_text(text, max_chars=240)
        return {"chunks": chunks, "characters": len(text), "chunksCount": len(chunks)}

    # -- tools -------------------------------------------------------------
    @app.get("/v1/tools")
    def list_tools(request: Request) -> dict[str, Any]:
        return {"tools": svc(request).tools.list(), "health": svc(request).tools.health()}

    @app.post("/v1/tools/{name}/run")
    def run_tool(request: Request, name: str, payload: ToolRunRequest) -> dict[str, Any]:
        result = svc(request).tools.execute(name, payload.arguments, confirmed=payload.confirmed)
        status_code = 200 if result.status in (ToolStatus.OK, ToolStatus.CONFIRMATION_REQUIRED) else 422
        if result.status is ToolStatus.UNAVAILABLE:
            status_code = 503
        if result.status is ToolStatus.DENIED:
            status_code = 403
        return JSONResponse(result.to_dict(), status_code=status_code)

    # -- Android app integration ------------------------------------------
    @app.get("/v1/apps")
    def list_apps(request: Request) -> dict[str, Any]:
        engine = svc(request).engine
        return {
            "catalog": engine.catalog(),
            "linked": [link.to_dict() for link in engine.registry.linked()],
            "connectors": [manifest.to_dict() for manifest in engine.registry.manifests()],
            "policy": engine.policy.to_dict(),
            "bridge": {"name": engine.bridge.name, "available": engine.bridge.available()},
            "history": svc(request).store.integration_history(),
        }

    @app.post("/v1/apps/discovery")
    def sync_discovery(request: Request, payload: DiscoveryRequest) -> dict[str, Any]:
        apps: list[DiscoveredApp] = []
        rejected: list[dict[str, str]] = []
        for item in payload.apps:
            try:
                apps.append(DiscoveredApp(
                    package_name=str(item.get("packageName", "")),
                    label=str(item.get("label", "")),
                    version_name=str(item.get("versionName", "0")),
                    version_code=int(item.get("versionCode", 0) or 0),
                ))
            except (IntegrationError, TypeError, ValueError) as exc:
                rejected.append({"packageName": str(item.get("packageName", ""))[:120], "reason": str(exc)[:160]})
        engine = svc(request).engine
        engine.sync_discovery(apps)
        return {"accepted": len(apps), "rejected": rejected, "total": len(engine.registry.discovered())}

    @app.post("/v1/apps/connectors")
    def import_connector(request: Request, payload: ConnectorRequest) -> dict[str, Any]:
        raw = payload.manifest
        try:
            actions = tuple(_parse_action(item) for item in raw.get("actions", []))
            manifest = ConnectorManifest(
                id=str(raw.get("id", "")),
                name=str(raw.get("name", "")),
                package_name=str(raw.get("packageName", "")),
                version=str(raw.get("version", "1.0")),
                level=IntegrationLevel(int(raw.get("level", 2))),
                actions=actions,
                auth=raw.get("auth", "none"),
                publisher=str(raw.get("publisher", ""))[:80],
                trusted=False,
                notes=str(raw.get("notes", ""))[:200],
            )
        except (IntegrationError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        svc(request).engine.register_connector(manifest)
        return {"connector": manifest.to_dict()}

    @app.post("/v1/apps/{package_name}/link")
    def link_app(request: Request, package_name: str, payload: LinkRequest) -> dict[str, Any]:
        try:
            return {"linked": svc(request).engine.link(package_name, granted_permissions=payload.grantedPermissions)}
        except IntegrationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/v1/apps/{package_name}/unlink")
    def unlink_app(request: Request, package_name: str) -> dict[str, Any]:
        try:
            return {"unlinked": svc(request).engine.unlink(package_name)}
        except IntegrationError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/v1/apps/{package_name}/permissions")
    def set_app_permissions(request: Request, package_name: str, payload: PermissionsRequest) -> dict[str, Any]:
        try:
            return {"link": svc(request).engine.set_permissions(package_name, payload.grantedPermissions)}
        except IntegrationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/v1/apps/{package_name}/enabled")
    def set_app_enabled(request: Request, package_name: str, payload: EnabledRequest) -> dict[str, Any]:
        try:
            return {"link": svc(request).engine.set_enabled(package_name, payload.enabled)}
        except IntegrationError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.put("/v1/apps/policy")
    def set_policy(request: Request, payload: PolicyRequest) -> dict[str, Any]:
        changes = payload.model_dump(exclude_none=True)
        mapped = {
            "max_level": changes.get("maxLevel"),
            "accessibility_opt_in": changes.get("accessibilityOptIn"),
            "blocked_packages": changes.get("blockedPackages"),
            "require_confirmation_for": changes.get("requireConfirmationFor"),
        }
        mapped = {key: value for key, value in mapped.items() if value is not None}
        try:
            policy = svc(request).engine.update_policy(**mapped)
        except (IntegrationError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        svc(request).store.set_setting("integration.policy", {
            "maxLevel": policy["maxLevel"],
            "accessibilityOptIn": policy["accessibilityOptIn"],
            "blockedPackages": policy["blockedPackages"],
            "requireConfirmationFor": policy["requireConfirmationFor"],
        })
        return {"policy": policy}

    @app.post("/v1/apps/resolve")
    def resolve_instruction(request: Request, payload: ResolveRequest) -> dict[str, Any]:
        engine = svc(request).engine
        try:
            preview = engine.describe(payload.instruction)
        except IntegrationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if payload.confirmed and preview["plan"]["steps"]:
            plan = engine.resolve(payload.instruction)
            preview["results"] = [result.to_dict() for result in engine.execute(plan, confirmed=True)]
        return preview

    # -- files -------------------------------------------------------------
    @app.post("/v1/files")
    async def upload_file(request: Request, file: UploadFile = File(...)) -> dict[str, Any]:
        services_now = svc(request)
        raw = await file.read(config.max_upload_bytes + 1)
        if len(raw) > config.max_upload_bytes:
            raise HTTPException(status_code=413, detail="El archivo supera el límite de subida.")
        name = re.sub(r"[^A-Za-z0-9._-]", "_", (file.filename or "archivo").rsplit("/", 1)[-1])[:120] or "archivo"
        identifier = uuid.uuid4().hex
        target = services_now.uploads / f"{identifier}-{name}"
        target.write_bytes(raw)
        text, note = _extract_text(target, file.content_type or "")
        return {
            "id": identifier,
            "name": name,
            "sizeBytes": len(raw),
            "mimeType": file.content_type or "application/octet-stream",
            "text": text[:40000],
            "textCharacters": len(text),
            "note": note,
        }

    @app.get("/v1/files")
    def list_files(request: Request) -> dict[str, Any]:
        services_now = svc(request)
        files = []
        for path in sorted(services_now.uploads.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True)[:200]:
            if not path.is_file():
                continue
            stat = path.stat()
            original = path.name.split("-", 1)[1] if "-" in path.name else path.name
            files.append({
                "id": path.name.split("-", 1)[0],
                "name": original,
                "sizeBytes": stat.st_size,
                "updatedAt": stat.st_mtime,
                "downloadPath": f"/v1/files/{path.name}",
            })
        return {"files": files}

    @app.get("/v1/files/{file_id}")
    def download_file(request: Request, file_id: str):
        from fastapi.responses import FileResponse

        services_now = svc(request)
        matches = _upload_matches(services_now.uploads, file_id)
        return FileResponse(str(matches[0]), filename=matches[0].name.split("-", 1)[1])

    @app.delete("/v1/files/{file_id}")
    def delete_file(request: Request, file_id: str) -> dict[str, Any]:
        services_now = svc(request)
        matches = _upload_matches(services_now.uploads, file_id)
        matches[0].unlink(missing_ok=True)
        return {"deleted": True}

    # -- chat --------------------------------------------------------------
    @app.post("/v1/chat")
    async def chat(request: Request, payload: ChatRequest) -> dict[str, Any]:
        return await _run_chat(svc(request), config, payload)

    @app.post("/v1/chat/stream")
    async def chat_stream(request: Request, payload: ChatRequest) -> StreamingResponse:
        services_now = svc(request)

        async def events() -> AsyncIterator[bytes]:
            queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()
            emitted = False

            async def emit(delta: str) -> None:
                await queue.put(("delta", {"text": delta}))

            task = asyncio.create_task(_run_chat(services_now, config, payload, allow_stream=True, emit=emit))
            while True:
                if task.done() and queue.empty():
                    break
                try:
                    kind, data = await asyncio.wait_for(queue.get(), timeout=0.05)
                except asyncio.TimeoutError:
                    continue
                if kind == "delta" and data.get("text"):
                    emitted = True
                yield _sse(kind, data)
            try:
                result = await task
            except HTTPException as exc:
                yield _sse("error", {"detail": exc.detail, "status": exc.status_code})
                return
            except Exception:
                yield _sse("error", {"detail": "La respuesta falló en el servidor.", "status": 500})
                return
            if not emitted:
                for chunk in chunk_text(result["message"]["content"], max_chars=160) or [result["message"]["content"]]:
                    if chunk:
                        yield _sse("delta", {"text": chunk + " "})
            yield _sse("meta", {
                "conversationId": result["conversationId"],
                "routing": result["routing"],
                "toolRuns": result["toolRuns"],
                "messageId": result["message"]["id"],
                "usage": result["usage"],
            })
            yield _sse("done", {"conversationId": result["conversationId"]})

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    # -- static web --------------------------------------------------------
    web_dir = Path(config.web_dir)
    if web_dir.exists():
        app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")

    return app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sse(event: str, data: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")


def _parse_action(raw: dict[str, Any]) -> ConnectorAction:
    from leyra_core.apps.models import ActionKind, ActionParameter, ParamType

    try:
        parameters = tuple(
            ActionParameter(
                name=str(item.get("name", "")),
                type=ParamType(str(item.get("type", "string"))),
                description=str(item.get("description", ""))[:240],
                required=bool(item.get("required", True)),
            )
            for item in raw.get("parameters", [])
        )
        return ConnectorAction(
            id=str(raw.get("id", "")),
            label=str(raw.get("label", "")),
            kind=ActionKind(str(raw.get("kind", "intent"))),
            level=IntegrationLevel(int(raw.get("level", 2))),
            description=str(raw.get("description", ""))[:400],
            parameters=parameters,
            permissions=tuple(str(p)[:60] for p in raw.get("permissions", [])),
            destructive=bool(raw.get("destructive", False)),
        )
    except (ValueError, TypeError) as exc:
        raise IntegrationError(f"Acción inválida: {exc}") from exc


_FILE_TOKEN = re.compile(r"^[A-Za-z0-9._-]{1,180}$")


def _upload_matches(uploads: Path, token: str) -> list[Path]:
    """Resolve a file id or a full stored name without allowing path traversal."""
    if not _FILE_TOKEN.fullmatch(token) or ".." in token:
        raise HTTPException(status_code=400, detail="Identificador inválido.")
    matches = [
        path for path in uploads.iterdir()
        if path.is_file() and (path.name == token or path.name.startswith(token + "-"))
    ]
    if not matches:
        raise HTTPException(status_code=404, detail="Archivo no encontrado.")
    return matches


def _extract_text(path: Path, mime: str) -> tuple[str, str]:
    if mime.startswith("text/") or mime in {"application/json", "application/xml"}:
        try:
            return path.read_text(encoding="utf-8", errors="replace")[:60000], "Texto extraído."
        except OSError:
            return "", "No se pudo leer el archivo."
    if mime == "application/pdf" or path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            pages = min(len(reader.pages), 40)
            text = "\n\n".join((reader.pages[i].extract_text() or "") for i in range(pages))
            return text[:60000], f"Extraídas {pages} de {len(reader.pages)} páginas."
        except ImportError:
            return "", "El servidor no tiene pypdf: el PDF se guardó pero no se pudo extraer texto."
        except Exception:
            return "", "No se pudo extraer texto del PDF."
    return "", "Tipo de archivo guardado sin extracción de texto."


def _system_prompt(services: Services, *, reasoning: bool, tool_names: Iterable[str]) -> str:
    memories = services.store.list_memories(limit=12)
    parts = [SYSTEM_PROMPT]
    if reasoning:
        parts.append(
            "Modo razonamiento: antes de responder, analiza el problema en pasos internos. "
            "Muestra solo un resumen breve del razonamiento y la respuesta final."
        )
    if memories:
        memory_lines = "\n".join(f"- {item['text']}" for item in memories)
        parts.append(f"Memoria autorizada del usuario (úsala solo si es relevante):\n{memory_lines}")
    names = sorted(tool_names)
    if names:
        parts.append(
            "Herramientas locales disponibles: " + ", ".join(names) +
            ". Úsalas cuando necesites un cálculo, una conversión o datos reales. "
            "Si una herramienta falla o no está disponible, dilo con claridad."
        )
    linked = [link for link in services.engine.registry.linked() if link.enabled]
    if linked:
        parts.append("Aplicaciones Android vinculadas: " + ", ".join(
            f"{link.label} (nivel {int(link.level)})" for link in linked))
    else:
        parts.append("No hay aplicaciones Android vinculadas en este entorno; la integración con apps requiere LEYRA en el móvil.")
    if not services.engine.bridge.available():
        parts.append("No hay puente Android conectado: no puedes ejecutar acciones en otras apps, solo planificarlas.")
    return "\n\n".join(parts)


def _history_turns(store, conversation_id: str, limit: int = 16) -> list[Turn]:
    conversation = store.get_conversation(conversation_id)
    turns: list[Turn] = []
    if not conversation:
        return turns
    for message in conversation["messages"][-limit:]:
        if message["role"] not in {"user", "assistant"}:
            continue
        text = message["content"]
        if len(text) > 6000:
            text = text[:6000] + " …"
        turns.append(Turn(role=message["role"], text=text))
    return turns


def _tool_schemas(services: Services) -> list[dict[str, Any]]:
    schemas = []
    for entry in services.tools.list():
        if not entry["available"] or entry["risk"] == "destructive":
            continue
        schema = {
            "type": "function",
            "function": {
                "name": tool_alias(entry["name"]),
                "description": f"{entry['title']}: {entry['description']}"[:1000],
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        }
        for parameter in entry["parameters"]:
            kind = {"number": "number", "integer": "integer", "boolean": "boolean",
                    "json": "object", "text": "string", "string": "string"}.get(parameter["kind"], "string")
            spec: dict[str, Any] = {"description": parameter["description"][:200] or parameter["name"]}
            if kind == "object":
                spec["type"] = "array" if parameter["name"] == "values" else "object"
                if parameter["name"] == "values":
                    spec["items"] = {"type": "number"}
            else:
                spec["type"] = kind
            if parameter["choices"]:
                spec["enum"] = parameter["choices"]
            if parameter.get("minimum") is not None:
                spec["minimum"] = parameter["minimum"]
            if parameter.get("maximum") is not None:
                spec["maximum"] = parameter["maximum"]
            schema["function"]["parameters"]["properties"][parameter["name"]] = spec
            if parameter["required"]:
                schema["function"]["parameters"]["required"].append(parameter["name"])
        schemas.append(schema)
    return schemas


async def _run_chat(services: Services, config: Settings, payload: ChatRequest, *,
                    allow_stream: bool = False, emit: Any = None) -> dict[str, Any]:
    store = services.store
    conversation_id = payload.conversationId
    if conversation_id:
        if store.get_conversation(conversation_id) is None:
            raise HTTPException(status_code=404, detail="Conversación no encontrada.")
    else:
        title = payload.message.strip().splitlines()[0][:60] or "Nueva conversación"
        conversation_id = store.create_conversation(title)["id"]

    try:
        requested = payload.model or config.default_model or None
        task = TaskKind.VISION if payload.images else (TaskKind.REASONING if payload.reasoning else TaskKind.CHAT)
        capabilities = {Capability.VISION} if payload.images else set()
        if payload.useTools:
            capabilities.add(Capability.TOOLS)
        decision = services.router.route(task=task, capabilities=capabilities, requested_model=requested)
    except RouterError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    client = build_client(decision.provider.id)
    if client is None:
        raise HTTPException(status_code=503, detail="El proveedor seleccionado no tiene credenciales en el servidor.")

    images = []
    for item in payload.images:
        try:
            images.append(parse_data_url(item))
        except ProviderError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    if images and not client.supports_images:
        raise HTTPException(status_code=422, detail="El adaptador del proveedor no admite imágenes en esta versión.")

    user_message = store.add_message(conversation_id, "user", payload.message,
                                     {"images": len(images), "model": decision.model.id})
    turns = _history_turns(store, conversation_id)
    # Replace the last stored turn with the multimodal version.
    if turns and turns[-1].role == "user":
        turns[-1] = Turn(role="user", text=payload.message, images=tuple(images))

    tool_schemas = _tool_schemas(services) if (payload.useTools and client.supports_tools) else []
    tool_names = [entry["name"] for entry in services.tools.list()]
    system = _system_prompt(services, reasoning=payload.reasoning, tool_names=tool_names)

    tool_runs: list[dict[str, Any]] = []
    text = ""
    usage: dict[str, Any] = {}
    try:
        if allow_stream and not tool_schemas:
            collected: list[str] = []
            async for delta in client.stream(model=decision.model.id, system=system, turns=turns,
                                             temperature=config.temperature,
                                             max_tokens=config.max_output_tokens):
                collected.append(delta)
                if emit is not None:
                    await emit(delta)
            text = "".join(collected).strip()
        else:
            for _ in range(MAX_TOOL_ROUNDS):
                response = await client.complete(
                    model=decision.model.id, system=system, turns=turns, tools=tool_schemas,
                    temperature=config.temperature, max_tokens=config.max_output_tokens,
                )
                usage = response.usage or usage
                if not response.tool_calls:
                    text = response.text
                    break
                turns.append(Turn(role="assistant", text=response.text,
                                  raw_tool_calls=tuple(_raw_call(call) for call in response.tool_calls)))
                for call in response.tool_calls:
                    name = _resolve_tool_name(services, call.name)
                    if name is None:
                        result_payload = {"status": "invalid", "detail": f"Herramienta desconocida: {call.name}"}
                    else:
                        outcome = services.tools.execute(name, call.arguments, confirmed=payload.confirmedTools)
                        result_payload = outcome.to_dict()
                        tool_runs.append({"tool": name, "arguments": call.arguments,
                                          "status": outcome.status.value, "detail": outcome.detail,
                                          "output": _jsonable(outcome.output)})
                    turns.append(Turn(role="tool", text=json.dumps(result_payload, ensure_ascii=False)[:8000],
                                      tool_call_id=call.id))
            if not text:
                text = "No pude completar la respuesta con las herramientas disponibles. ¿Quieres reformular la solicitud?"
    except ProviderError as exc:
        store.delete_conversation_messages(conversation_id, user_message["createdAt"] - 0.001)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not text.strip():
        text = "El proveedor devolvió una respuesta vacía."

    assistant = store.add_message(conversation_id, "assistant", text, {
        "model": decision.model.id,
        "provider": decision.provider.id,
        "toolRuns": tool_runs,
        "usage": usage,
        "reasoning": payload.reasoning,
    })
    return {
        "conversationId": conversation_id,
        "message": assistant,
        "userMessageId": user_message["id"],
        "routing": {
            "model": decision.model.id,
            "provider": decision.provider.id,
            "reason": decision.reason,
            "fallbacks": [m.id for m in decision.fallbacks],
        },
        "toolRuns": tool_runs,
        "usage": usage,
    }


def _raw_call(call) -> dict[str, Any]:
    return {
        "id": call.id,
        "type": "function",
        "function": {"name": tool_alias(call.name), "arguments": json.dumps(call.arguments, ensure_ascii=False)},
    }


def _resolve_tool_name(services: Services, alias: str) -> str | None:
    """Map a provider-facing tool alias (``a__b``) back to its real name."""
    needle = tool_alias(alias)
    for entry in services.tools.list():
        if tool_alias(entry["name"]) == needle:
            return entry["name"]
    return None


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


app = create_app()
