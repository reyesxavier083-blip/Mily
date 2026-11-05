"""Pure ASGI guard: origin allowlist, bearer auth, rate limiting, size limits.

Written as raw ASGI (instead of ``BaseHTTPMiddleware``) so early rejections and
streamed responses keep correct framing and security headers.
"""

from __future__ import annotations

import hmac
import json
import time

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import RateLimiter, Settings

_SENSITIVE_PREFIXES = ("/v1/",)
_NO_STORE_PATHS = frozenset({"/", "/index.html", "/styles.css", "/app.js"})


class SecurityGuard:
    def __init__(self, app: ASGIApp, *, config: Settings, limiter: RateLimiter) -> None:
        self.app = app
        self.config = config
        self.limiter = limiter

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        origin = (headers.get("origin") or "").rstrip("/")
        host = (headers.get("host") or "").rstrip("/")
        forwarded = (headers.get("x-forwarded-host") or "").split(",")[0].strip().rstrip("/")
        origin_host = origin.split("://")[-1] if origin else ""
        allowed_origin = origin.rstrip("/") in self.config.allowed_origins
        same_origin = bool(origin_host) and origin_host in {host, forwarded}

        if origin and not allowed_origin and not same_origin:
            await _send_json(send, 403, "Origen no permitido.")
            return
        if scope["method"] == "OPTIONS":
            await _send_json(send, 204, None, extra=[("access-control-allow-methods", "GET, POST, PUT, DELETE, OPTIONS")])
            return

        path = scope.get("path", "")
        if path.startswith(_SENSITIVE_PREFIXES):
            if self.config.auth_required:
                supplied = headers.get("authorization", "")
                token = supplied[7:].strip() if supplied.lower().startswith("bearer ") else ""
                if not hmac.compare_digest(token.encode("utf-8"), self.config.api_token.encode("utf-8")):
                    await _send_json(send, 401, "No autorizado.")
                    return
            client = scope.get("client") or ("unknown", 0)
            if not self.limiter.allow(str(client[0]), now=time.time()):
                await _send_json(send, 429, "Demasiadas solicitudes. Inténtalo en un minuto.")
                return
            length = headers.get("content-length")
            if length and length.isdigit() and int(length) > self.config.max_body_bytes:
                await _send_json(send, 413, "La solicitud es demasiado grande.")
                return

        no_store = path in _NO_STORE_PATHS

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                mutable = MutableHeaders(scope=message)
                mutable.setdefault("x-content-type-options", "nosniff")
                mutable.setdefault("referrer-policy", "no-referrer")
                if no_store:
                    mutable["cache-control"] = "no-store"
            await send(message)

        await self.app(scope, receive, send_wrapper)


async def _send_json(send: Send, status: int, detail: str | None, extra: list[tuple[str, str]] | None = None) -> None:
    payload = b"" if detail is None else json.dumps({"detail": detail}, ensure_ascii=False).encode("utf-8")
    headers = [(b"content-length", str(len(payload)).encode("ascii"))]
    if detail is not None:
        headers.append((b"content-type", b"application/json; charset=utf-8"))
    for key, value in extra or []:
        headers.append((key.encode("latin-1"), value.encode("latin-1")))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": payload})
