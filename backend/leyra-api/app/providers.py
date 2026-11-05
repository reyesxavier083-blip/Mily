"""Provider adapters. Keys live in the process environment, never in payloads."""

from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

import httpx


class ProviderError(RuntimeError):
    """A provider call failed. Messages are safe to show to the user."""


@dataclass(frozen=True)
class ImagePart:
    mime_type: str
    data_base64: str


@dataclass(frozen=True)
class Turn:
    """One conversation turn in a provider-neutral shape.

    ``tool`` turns carry a ``tool_call_id``; assistant turns produced by a tool
    round carry ``raw_tool_calls`` so OpenAI-compatible providers keep the
    canonical protocol.
    """

    role: str  # user | assistant | tool
    text: str
    images: tuple[ImagePart, ...] = ()
    tool_call_id: str = ""
    raw_tool_calls: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"role": self.role, "text": self.text[:20000], "images": len(self.images),
                "toolCallId": self.tool_call_id}


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ProviderResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    finish_reason: str = ""


_DATA_URL = re.compile(r"^data:(image/[a-zA-Z0-9.+-]+);base64,([A-Za-z0-9+/=\s]+)$")


def parse_data_url(value: str, *, max_bytes: int = 6 * 1024 * 1024) -> ImagePart:
    match = _DATA_URL.match(str(value).strip())
    if not match:
        raise ProviderError("La imagen adjunta no es un data URL base64 válido.")
    mime_type, encoded = match.group(1), re.sub(r"\s+", "", match.group(2))
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise ProviderError("La imagen adjunta está corrupta.") from exc
    if len(raw) > max_bytes:
        raise ProviderError("La imagen supera el tamaño máximo permitido (6 MB).")
    if not raw:
        raise ProviderError("La imagen adjunta está vacía.")
    return ImagePart(mime_type=mime_type, data_base64=base64.b64encode(raw).decode("ascii"))


class ProviderClient:
    """Base adapter."""

    id = "base"
    supports_tools = False
    supports_images = False
    supports_stream = False

    def __init__(self, *, key: str, base_url: str, timeout: float = 90.0) -> None:
        self._key = key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self._key and self._base_url)

    async def complete(self, *, model: str, system: str, turns: Sequence[Turn],
                       tools: Iterable[dict[str, Any]] = (), temperature: float = 0.6,
                       max_tokens: int = 1200) -> ProviderResponse:
        raise NotImplementedError

    async def stream(self, *, model: str, system: str, turns: Sequence[Turn],
                     temperature: float = 0.6, max_tokens: int = 1200):
        """Yield text deltas. Default: one final delta from ``complete``."""
        response = await self.complete(model=model, system=system, turns=turns,
                                       temperature=temperature, max_tokens=max_tokens)
        if response.text:
            yield response.text

    async def _post(self, path: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderError("El proveedor de IA no respondió a tiempo.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("No se pudo conectar con el proveedor de IA.") from exc
        if response.status_code == 401:
            raise ProviderError("El proveedor rechazó la credencial configurada.")
        if response.status_code == 429:
            raise ProviderError("El proveedor limitó las solicitudes. Inténtalo en unos segundos.")
        if response.status_code >= 400:
            detail = ""
            try:
                body = response.json()
                detail = str(body.get("error", {}).get("message") or body.get("error") or "")
            except ValueError:
                detail = ""
            detail = re.sub(r"\s+", " ", detail)[:200]
            raise ProviderError(f"El proveedor devolvió un error ({response.status_code}). {detail}".strip())
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError("El proveedor devolvió una respuesta ilegible.") from exc


class OpenAICompatibleClient(ProviderClient):
    """OpenAI, Azure-compatible gateways and local Ollama `/v1` endpoints."""

    id = "openai-compatible"
    supports_tools = True
    supports_images = True
    supports_stream = True

    def _messages(self, system: str, turns: Sequence[Turn]) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        for turn in turns:
            if turn.role == "tool":
                messages.append({"role": "tool", "tool_call_id": turn.tool_call_id, "content": turn.text})
                continue
            if turn.role == "assistant" and turn.raw_tool_calls:
                messages.append({"role": "assistant", "content": turn.text or None,
                                 "tool_calls": list(turn.raw_tool_calls)})
                continue
            if turn.images:
                content: list[dict[str, Any]] = [{"type": "text", "text": turn.text or " "}]
                for image in turn.images:
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{image.mime_type};base64,{image.data_base64}"},
                    })
                messages.append({"role": turn.role, "content": content})
            else:
                messages.append({"role": turn.role, "content": turn.text})
        return messages

    async def complete(self, *, model: str, system: str, turns: Sequence[Turn],
                       tools: Iterable[dict[str, Any]] = (), temperature: float = 0.6,
                       max_tokens: int = 1200) -> ProviderResponse:
        payload: dict[str, Any] = {
            "model": model,
            "messages": self._messages(system, turns),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        tool_list = list(tools)
        if tool_list:
            payload["tools"] = tool_list
            payload["tool_choice"] = "auto"
        data = await self._post("/chat/completions", payload,
                                {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"})
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError("El proveedor no devolvió ninguna respuesta.")
        message = choices[0].get("message") or {}
        calls: list[ToolCall] = []
        for index, call in enumerate(message.get("tool_calls") or []):
            function = call.get("function") or {}
            try:
                arguments = json.loads(function.get("arguments") or "{}")
            except ValueError:
                arguments = {}
            calls.append(ToolCall(
                id=str(call.get("id") or f"call_{index}"),
                name=str(function.get("name") or ""),
                arguments=arguments if isinstance(arguments, dict) else {},
            ))
        return ProviderResponse(
            text=str(message.get("content") or "").strip(),
            tool_calls=calls,
            usage=data.get("usage") or {},
            finish_reason=str(choices[0].get("finish_reason") or ""),
        )

    async def stream(self, *, model: str, system: str, turns: Sequence[Turn],
                     temperature: float = 0.6, max_tokens: int = 1200):
        payload = {
            "model": model,
            "messages": self._messages(system, turns),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        url = f"{self._base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    if response.status_code >= 400:
                        raise ProviderError(f"El proveedor devolvió un error ({response.status_code}).")
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        chunk = line[5:].strip()
                        if not chunk or chunk == "[DONE]":
                            continue
                        try:
                            event = json.loads(chunk)
                        except ValueError:
                            continue
                        for choice in event.get("choices") or []:
                            delta = (choice.get("delta") or {}).get("content")
                            if isinstance(delta, str) and delta:
                                yield delta
        except httpx.TimeoutException as exc:
            raise ProviderError("La respuesta del proveedor se interrumpió por tiempo de espera.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("Se perdió la conexión con el proveedor de IA.") from exc


class AnthropicClient(ProviderClient):
    supports_images = True

    def __init__(self, *, key: str, base_url: str, timeout: float = 90.0) -> None:
        super().__init__(key=key, base_url=base_url, timeout=timeout)

    def _content(self, turn: Turn) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        for image in turn.images:
            blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": image.mime_type, "data": image.data_base64},
            })
        if turn.text:
            blocks.append({"type": "text", "text": turn.text})
        return blocks

    async def complete(self, *, model: str, system: str, turns: Sequence[Turn],
                       tools: Iterable[dict[str, Any]] = (), temperature: float = 0.6,
                       max_tokens: int = 1200) -> ProviderResponse:
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": t.role, "content": self._content(t)} for t in turns],
        }
        data = await self._post("/v1/messages", payload, {
            "x-api-key": self._key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        })
        text = "".join(
            block.get("text", "") for block in (data.get("content") or [])
            if isinstance(block, dict) and block.get("type") == "text"
        )
        return ProviderResponse(text=text.strip(), usage=data.get("usage") or {},
                                finish_reason=str(data.get("stop_reason") or ""))


class GoogleClient(ProviderClient):
    supports_images = True

    async def complete(self, *, model: str, system: str, turns: Sequence[Turn],
                       tools: Iterable[dict[str, Any]] = (), temperature: float = 0.6,
                       max_tokens: int = 1200) -> ProviderResponse:
        contents = []
        for turn in turns:
            parts: list[dict[str, Any]] = [{"text": turn.text or " "}]
            for image in turn.images:
                parts.append({"inline_data": {"mime_type": image.mime_type, "data": image.data_base64}})
            contents.append({"role": "user" if turn.role == "user" else "model", "parts": parts})
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        data = await self._post(
            f"/v1beta/models/{model}:generateContent",
            payload,
            {"x-goog-api-key": self._key, "Content-Type": "application/json"},
        )
        chunks: list[str] = []
        for candidate in data.get("candidates") or []:
            for part in (candidate.get("content") or {}).get("parts") or []:
                if isinstance(part.get("text"), str):
                    chunks.append(part["text"])
        return ProviderResponse(text="".join(chunks).strip(),
                                usage=data.get("usageMetadata") or {})


def build_client(provider_id: str, env: Mapping[str, str] | None = None) -> ProviderClient | None:
    source = env if env is not None else os.environ

    def get(key: str, default: str = "") -> str:
        return str(source.get(key, default)).strip()

    if provider_id == "openai":
        key = get("OPENAI_API_KEY")
        return OpenAICompatibleClient(key=key, base_url=get("OPENAI_BASE_URL", "https://api.openai.com/v1")) if key else None
    if provider_id == "anthropic":
        key = get("ANTHROPIC_API_KEY")
        return AnthropicClient(key=key, base_url=get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")) if key else None
    if provider_id == "google":
        key = get("GOOGLE_API_KEY")
        return GoogleClient(key=key, base_url=get("GOOGLE_BASE_URL", "https://generativelanguage.googleapis.com")) if key else None
    if provider_id == "local":
        base = get("LEYRA_LOCAL_MODEL_URL")
        return OpenAICompatibleClient(key=get("LEYRA_LOCAL_MODEL_KEY", "local"), base_url=f"{base}/v1") if base else None
    return None
