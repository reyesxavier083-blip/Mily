"""LEYRA multimodel engine: registry, provider manager, router and fallbacks.

Only environment variable *names* are handled here. A provider is reported as
configured when its key variable is present and non-empty; the value is never
read into a response, a log or the frontend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import os
from typing import Any, Iterable, Mapping


class Capability(str, Enum):
    TEXT = "text"
    VISION = "vision"
    TOOLS = "tools"
    AUDIO = "audio"
    JSON_MODE = "json"
    STREAMING = "streaming"
    LONG_CONTEXT = "long_context"


class TaskKind(str, Enum):
    CHAT = "chat"
    REASONING = "reasoning"
    CODING = "coding"
    VISION = "vision"
    TRANSCRIPTION = "transcription"
    SPEECH = "speech"
    EMBEDDING = "embedding"


class RouterError(ValueError):
    """Raised when no model can satisfy a request."""


@dataclass(frozen=True)
class ModelEntry:
    id: str
    provider: str
    label: str
    capabilities: frozenset[Capability]
    context_window: int = 128_000
    cost_tier: int = 2
    tasks: frozenset[TaskKind] = frozenset({TaskKind.CHAT})
    local: bool = False
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.id or not self.provider:
            raise RouterError("Model id and provider are required")
        if self.context_window <= 0:
            raise RouterError("context_window must be positive")
        if self.cost_tier not in (0, 1, 2, 3):
            raise RouterError("cost_tier must be 0..3")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "provider": self.provider,
            "label": self.label,
            "capabilities": sorted(cap.value for cap in self.capabilities),
            "contextWindow": self.context_window,
            "costTier": self.cost_tier,
            "tasks": sorted(task.value for task in self.tasks),
            "local": self.local,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class Provider:
    """A model vendor. ``key_env`` is the *name* of the secret env variable."""

    id: str
    label: str
    key_env: str
    base_url: str = ""
    kind: str = "openai-compatible"

    def configured(self, env: Mapping[str, str] | None = None) -> bool:
        source = env if env is not None else os.environ
        return bool(str(source.get(self.key_env, "")).strip())

    def to_dict(self, env: Mapping[str, str] | None = None) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "keyEnv": self.key_env,
            "baseUrl": self.base_url,
            "kind": self.kind,
            "configured": self.configured(env),
        }


DEFAULT_PROVIDERS: tuple[Provider, ...] = (
    Provider("openai", "OpenAI", "OPENAI_API_KEY", "https://api.openai.com/v1"),
    Provider("anthropic", "Anthropic", "ANTHROPIC_API_KEY", "https://api.anthropic.com"),
    Provider("google", "Google AI", "GOOGLE_API_KEY", "https://generativelanguage.googleapis.com"),
    Provider("local", "Modelo local (Ollama)", "LEYRA_LOCAL_MODEL_URL", "http://127.0.0.1:11434", kind="local"),
)

DEFAULT_MODELS: tuple[ModelEntry, ...] = (
    ModelEntry("gpt-4o-mini", "openai", "OpenAI GPT-4o mini",
               frozenset({Capability.TEXT, Capability.VISION, Capability.TOOLS, Capability.JSON_MODE,
                          Capability.STREAMING}), 128_000, 1,
               frozenset({TaskKind.CHAT, TaskKind.VISION})),
    ModelEntry("gpt-4o", "openai", "OpenAI GPT-4o",
               frozenset({Capability.TEXT, Capability.VISION, Capability.TOOLS, Capability.JSON_MODE,
                          Capability.STREAMING}), 128_000, 2,
               frozenset({TaskKind.CHAT, TaskKind.REASONING, TaskKind.CODING, TaskKind.VISION})),
    ModelEntry("gpt-4.1", "openai", "OpenAI GPT-4.1",
               frozenset({Capability.TEXT, Capability.VISION, Capability.TOOLS, Capability.JSON_MODE,
                          Capability.STREAMING, Capability.LONG_CONTEXT}), 1_000_000, 3,
               frozenset({TaskKind.CHAT, TaskKind.REASONING, TaskKind.CODING, TaskKind.VISION})),
    ModelEntry("claude-3-5-sonnet-latest", "anthropic", "Claude 3.5 Sonnet",
               frozenset({Capability.TEXT, Capability.VISION, Capability.TOOLS, Capability.STREAMING,
                          Capability.LONG_CONTEXT}), 200_000, 2,
               frozenset({TaskKind.CHAT, TaskKind.REASONING, TaskKind.CODING, TaskKind.VISION})),
    ModelEntry("gemini-1.5-flash", "google", "Google Gemini 1.5 Flash",
               frozenset({Capability.TEXT, Capability.VISION, Capability.TOOLS, Capability.STREAMING,
                          Capability.LONG_CONTEXT}), 1_000_000, 1,
               frozenset({TaskKind.CHAT, TaskKind.VISION, TaskKind.REASONING})),
    ModelEntry("llama3.2", "local", "Llama 3.2 (local)",
               frozenset({Capability.TEXT, Capability.STREAMING}), 8_192, 0,
               frozenset({TaskKind.CHAT}), local=True,
               notes="Requiere un servidor local compatible con Ollama."),
)


class ModelRegistry:
    def __init__(self, models: Iterable[ModelEntry] = DEFAULT_MODELS) -> None:
        self._models: dict[str, ModelEntry] = {}
        for model in models:
            self.register(model)

    def register(self, model: ModelEntry) -> ModelEntry:
        if model.id in self._models:
            raise RouterError(f"Modelo duplicado: {model.id}")
        self._models[model.id] = model
        return model

    def get(self, model_id: str) -> ModelEntry | None:
        return self._models.get(model_id)

    def all(self) -> list[ModelEntry]:
        return sorted(self._models.values(), key=lambda m: (m.provider, m.id))

    def matching(self, *, task: TaskKind | None = None, capabilities: Iterable[Capability] = (),
                 max_cost_tier: int = 3, prefer_local: bool = False) -> list[ModelEntry]:
        required = set(capabilities)
        candidates = []
        for model in self._models.values():
            if task is not None and task not in model.tasks:
                continue
            if not required.issubset(model.capabilities):
                continue
            if model.cost_tier > max_cost_tier:
                continue
            if task is TaskKind.VISION and Capability.VISION not in model.capabilities:
                continue
            candidates.append(model)
        candidates.sort(key=lambda m: (0 if (prefer_local and m.local) else 1, m.cost_tier, -m.context_window))
        return candidates


@dataclass(frozen=True)
class RoutingDecision:
    model: ModelEntry
    provider: Provider
    fallbacks: tuple[ModelEntry, ...] = ()
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model.to_dict(),
            "provider": self.provider.to_dict(),
            "fallbacks": [m.to_dict() for m in self.fallbacks],
            "reason": self.reason,
        }


class ModelRouter:
    """Capability-based routing with an explicit, explainable fallback chain."""

    def __init__(self, registry: ModelRegistry | None = None,
                 providers: Iterable[Provider] = DEFAULT_PROVIDERS,
                 env: Mapping[str, str] | None = None) -> None:
        self.registry = registry or ModelRegistry()
        self.providers: dict[str, Provider] = {p.id: p for p in providers}
        self._env = env

    def env(self) -> Mapping[str, str]:
        return self._env if self._env is not None else os.environ

    def configured_models(self) -> list[ModelEntry]:
        return [m for m in self.registry.all()
                if (provider := self.providers.get(m.provider)) and provider.configured(self.env())]

    def route(self, *, task: TaskKind = TaskKind.CHAT, capabilities: Iterable[Capability] = (),
              max_cost_tier: int = 3, prefer_local: bool = False,
              requested_model: str | None = None) -> RoutingDecision:
        available = {m.id for m in self.configured_models()}
        if not available:
            raise RouterError(
                "No hay proveedores de IA configurados en el servidor. Define la variable de entorno "
                "correspondiente (por ejemplo OPENAI_API_KEY) para habilitar el chat."
            )
        if requested_model:
            model = self.registry.get(requested_model)
            if model is None:
                raise RouterError(f"Modelo desconocido: {requested_model}")
            provider = self.providers.get(model.provider)
            if provider is None or not provider.configured(self.env()):
                raise RouterError(f"El proveedor de {model.label} no está configurado en el servidor.")
            return RoutingDecision(model, provider, (), "Modelo solicitado explícitamente.")
        candidates = [m for m in self.registry.matching(task=task, capabilities=capabilities,
                                                        max_cost_tier=max_cost_tier,
                                                        prefer_local=prefer_local)]
        usable = [m for m in candidates if m.id in available]
        if not usable:
            raise RouterError(
                "Ningún modelo configurado cubre las capacidades requeridas "
                f"({', '.join(sorted(c.value for c in set(capabilities))) or 'texto'})."
            )
        chosen = usable[0]
        provider = self.providers[chosen.provider]
        fallbacks = tuple(m for m in usable[1:4])
        reason = (f"Seleccionado por capacidades {', '.join(sorted(c.value for c in chosen.capabilities))} "
                  f"con coste {chosen.cost_tier}.")
        return RoutingDecision(chosen, provider, fallbacks, reason)

    def health(self) -> dict[str, Any]:
        configured = self.configured_models()
        return {
            "module": "ai-engine",
            "status": "ok" if configured else "unavailable",
            "providers": [p.to_dict(self.env()) for p in self.providers.values()],
            "models": [m.to_dict() for m in self.registry.all()],
            "configuredModels": [m.id for m in configured],
            "detail": (
                f"{len(configured)} modelos disponibles." if configured
                else "Sin credenciales de proveedor: el chat no puede ejecutarse."
            ),
        }
