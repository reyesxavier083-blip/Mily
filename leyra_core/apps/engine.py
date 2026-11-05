"""LEYRA ANDROID APP INTEGRATION ENGINE.

Responsibilities:

* ingest what the Android bridge discovered (``PackageManager``);
* resolve natural-language instructions into reviewable plans using only
  documented connector actions;
* refuse anything the security policy does not allow;
* dispatch approved steps through a platform bridge and record the outcome.

The engine never fabricates an execution: when no Android bridge is connected,
every dispatch returns ``unavailable`` with a truthful explanation.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable, Protocol

from .models import (
    ActionKind,
    ActionStep,
    CapabilityStatus,
    ConnectorAction,
    ConnectorManifest,
    DiscoveredApp,
    ExecutionResult,
    ExecutionStatus,
    IntegrationError,
    IntegrationLevel,
    IntegrationPlan,
)
from .policy import IntegrationPolicy
from .registry import AppRegistry


class PlatformBridge(Protocol):
    """Adapter implemented by the Android layer (or a test double)."""

    name: str

    def available(self) -> bool:
        """Whether this bridge can really dispatch intents right now."""

    def dispatch(self, step: ActionStep) -> ExecutionResult:
        """Carry out one step using public Android mechanisms only."""


class UnavailableBridge:
    """Default bridge when LEYRA runs off-device (web/backend)."""

    name = "none"

    def available(self) -> bool:
        return False

    def dispatch(self, step: ActionStep) -> ExecutionResult:
        return ExecutionResult(
            status=ExecutionStatus.UNAVAILABLE,
            connector_id=step.connector_id,
            action_id=step.action_id,
            detail=(
                "No hay un dispositivo Android conectado: la acción se planificó pero no se ejecutó. "
                "Abre LEYRA en el móvil para lanzarla."
            ),
        )


def normalize(text: str) -> str:
    """Lowercase, strip accents and question marks, collapse whitespace."""
    decomposed = unicodedata.normalize("NFD", str(text))
    plain = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    plain = re.sub(r"[¿?¡!\u201c\u201d\u00ab\u00bb]", " ", plain)
    return re.sub(r"\s+", " ", plain.lower()).strip()


_OPEN = re.compile(r"^(?:abre|abrir|abreme|abreme la|lanza|lanzar|inicia|ejecuta)\s+(?:la\s+)?(?:app|aplicacion)?\s*(.+)$")
_SHARE = re.compile(
    r"^(?:comparte|compartir|envia|enviar|manda|mandar)\s+"
    r"(?:el\s+|este\s+|la\s+)?(texto|archivo|documento|enlace|link|imagen|foto)?\s*"
    r"(.*?)\s*\b(?:con|a|en|usando|mediante)\b\s+(.+)$"
)
_OPEN_LINK = re.compile(r"^(?:abre|abrir|visita|abrir enlace)\s+(https?://\S+)(?:\s+(?:en|con)\s+(.+))?$")
_WHO_CAN = re.compile(r"^(?:que|qué|cuales|cuáles)?\s*(?:aplicaciones|apps)\s*(?:pueden|puede|sirven para|hay para)\s+(.+)$")
_LIST_LINKED = re.compile(
    r"^(?:muestrame|muéstrame|lista|listar|ver|ensename)\s+(?:mis\s+|las\s+|los\s+)?"
    r"(?:aplicaciones\s+vinculadas|apps\s+vinculadas|aplicaciones\s+conectadas)$"
)


class AppIntegrationEngine:
    """Coordinates discovery, linking, planning and execution."""

    def __init__(
        self,
        registry: AppRegistry | None = None,
        policy: IntegrationPolicy | None = None,
        bridge: PlatformBridge | None = None,
    ) -> None:
        self.registry = registry or AppRegistry()
        self.policy = policy or IntegrationPolicy()
        self.bridge: PlatformBridge = bridge or UnavailableBridge()

    # -- discovery ---------------------------------------------------------
    def sync_discovery(self, apps: Iterable[DiscoveredApp]) -> list[DiscoveredApp]:
        return self.registry.sync_discovered(apps)

    def register_connector(self, manifest: ConnectorManifest) -> ConnectorManifest:
        return self.registry.upsert_manifest(manifest)

    def catalog(self) -> list[dict[str, Any]]:
        """Installed apps annotated with real compatibility information."""
        entries: list[dict[str, Any]] = []
        for app in self.registry.discovered():
            manifest = self.registry.manifest(app.package_name)
            link = self.registry.linked_app(app.package_name)
            if manifest is None:
                status = CapabilityStatus.OPEN_ONLY
                note = "Sin conector documentado: solo puede abrirse con un intent de lanzamiento."
                level = IntegrationLevel.OPEN
                actions: list[ConnectorAction] = []
            else:
                status = CapabilityStatus.FULL if manifest.actions else CapabilityStatus.INCOMPATIBLE
                note = manifest.notes
                level = manifest.level
                actions = list(manifest.actions)
            if manifest is not None and not manifest.actions:
                status = CapabilityStatus.INCOMPATIBLE
            if level > self.policy.effective_level():
                status = CapabilityStatus.OPEN_ONLY if level > IntegrationLevel.OPEN else CapabilityStatus.PARTIAL
                note = f"Requiere nivel {int(level)}; la política actual permite hasta {int(self.policy.effective_level())}."
            entries.append({
                "packageName": app.package_name,
                "label": app.label,
                "versionName": app.version_name,
                "versionCode": app.version_code,
                "connectorId": manifest.id if manifest else "",
                "level": int(level),
                "status": status.value,
                "linked": link is not None and link.enabled,
                "note": note,
                "actions": [a.id for a in actions],
            })
        return entries

    def link(self, package_name: str, *, granted_permissions: Iterable[str] = ()) -> dict[str, Any]:
        self.policy.check_package(package_name)
        app = self.registry.discovered_app(package_name)
        if app is None:
            raise IntegrationError("La aplicación no está instalada o no fue descubierta.")
        manifest = self.registry.manifest(package_name)
        if manifest is None:
            # Level 1 is always possible through a public launch intent.
            manifest = ConnectorManifest(
                id=f"open.{package_name}",
                name=f"Apertura de {app.label}",
                package_name=package_name,
                version=app.version_name if re.fullmatch(r"[0-9]+(\.[0-9]+){0,3}", app.version_name) else "1.0",
                level=IntegrationLevel.OPEN,
                actions=(ConnectorAction(
                    id="open_app",
                    label=f"Abrir {app.label}",
                    kind=ActionKind.LAUNCH,
                    level=IntegrationLevel.OPEN,
                    description="Abre la aplicación con un intent de lanzamiento público.",
                ),),
                notes="Integración de solo apertura: la app no documenta otras interfaces públicas.",
            )
            self.registry.upsert_manifest(manifest)
        self.policy.check_level(manifest.level)
        link = self.registry.link(package_name, granted_permissions=granted_permissions)
        return link.to_dict()

    def unlink(self, package_name: str) -> dict[str, Any]:
        return self.registry.unlink(package_name).to_dict()

    def set_permissions(self, package_name: str, permissions: Iterable[str]) -> dict[str, Any]:
        return self.registry.set_permissions(package_name, permissions).to_dict()

    def set_enabled(self, package_name: str, enabled: bool) -> dict[str, Any]:
        return self.registry.set_enabled(package_name, enabled).to_dict()

    def update_policy(self, **changes: Any) -> dict[str, Any]:
        self.policy = self.policy.update(**changes)
        return self.policy.to_dict()

    # -- capabilities ------------------------------------------------------
    def actions_for(self, package_name: str) -> list[ConnectorAction]:
        manifest = self.registry.manifest(package_name)
        return list(manifest.actions) if manifest else []

    def find_capabilities(self, query: str, *, linked_only: bool = False) -> list[dict[str, Any]]:
        """Search documented actions by keyword (label, id, description)."""
        needle = normalize(query)
        if not needle:
            raise IntegrationError("Indica qué capacidad buscas.")
        scored: list[tuple[int, dict[str, Any]]] = []
        linked = {link.package_name for link in self.registry.linked() if link.enabled}
        for manifest in self.registry.manifests():
            if linked_only and manifest.package_name not in linked:
                continue
            for action in manifest.actions:
                haystack = normalize(" ".join([action.label, action.id, action.description, manifest.name]))
                score = sum(1 for token in needle.split() if token in haystack)
                if score:
                    scored.append((score, {
                        "packageName": manifest.package_name,
                        "appLabel": manifest.name,
                        "connectorId": manifest.id,
                        "action": action.id,
                        "label": action.label,
                        "level": int(action.level),
                        "linked": manifest.package_name in linked,
                        "requiresConfirmation": self.policy.needs_confirmation(action.kind.value, destructive=action.destructive),
                    }))
        scored.sort(key=lambda item: (-item[0], item[1]["appLabel"].lower()))
        return [entry for _, entry in scored]

    # -- instruction resolution -------------------------------------------
    def resolve(self, instruction: str) -> IntegrationPlan:
        """Turn a user instruction into an executable, reviewable plan."""
        text = normalize(instruction)
        if not text:
            raise IntegrationError("La instrucción está vacía.")
        if _LIST_LINKED.fullmatch(text):
            return IntegrationPlan(instruction=instruction, steps=(), notes=("__list_linked__",))
        match = _WHO_CAN.fullmatch(text)
        if match:
            return IntegrationPlan(instruction=instruction, steps=(), notes=(f"__capabilities__:{match.group(1)}",))
        match = _OPEN_LINK.fullmatch(text)
        if match:
            return self._plan_open_link(instruction, match.group(1), match.group(2))
        match = _OPEN.fullmatch(text)
        if match:
            return self._plan_open(instruction, match.group(1))
        match = _SHARE.fullmatch(text)
        if match:
            kind = match.group(1) or "texto"
            payload = match.group(2) or ""
            target = match.group(3)
            # Recover the original casing: matching runs on a normalized copy,
            # but the text the user shares must be sent verbatim.
            raw = re.sub(r"[¿?¡!]+", " ", str(instruction)).strip()
            raw_match = re.fullmatch(_SHARE.pattern, raw, re.IGNORECASE)
            if raw_match:
                kind = raw_match.group(1) or kind
                payload = raw_match.group(2) or payload
                target = raw_match.group(3) or target
            return self._plan_share(instruction, kind, payload, target)
        raise IntegrationError(
            "No reconozco una acción de integración en esa frase. Puedo abrir apps, compartir texto o "
            "archivos, abrir enlaces y buscar qué aplicaciones pueden hacer una tarea."
        )

    def _resolve_target(self, raw: str) -> tuple[str, ConnectorManifest]:
        needle = normalize(raw)
        candidates = []
        for manifest in self.registry.manifests():
            app = self.registry.discovered_app(manifest.package_name)
            label = app.label if app else manifest.name
            if needle in normalize(label) or needle in normalize(manifest.name) or needle == normalize(manifest.package_name):
                candidates.append(manifest)
        if not candidates:
            for app in self.registry.discovered():
                if needle in normalize(app.label) or needle == normalize(app.package_name):
                    manifest = self.registry.manifest(app.package_name)
                    if manifest is not None:
                        candidates.append(manifest)
        if not candidates:
            raise IntegrationError(f"No encuentro una aplicación instalada que coincida con «{raw}».")
        if len(candidates) > 1:
            names = ", ".join(m.name for m in candidates)
            raise IntegrationError(f"«{raw}» coincide con varias aplicaciones ({names}). Indica el paquete exacto.")
        manifest = candidates[0]
        self.policy.check_package(manifest.package_name)
        self.policy.check_level(manifest.level)
        return manifest.package_name, manifest

    def _require_linked(self, manifest: ConnectorManifest) -> None:
        link = self.registry.linked_app(manifest.package_name)
        if link is None or not link.enabled:
            raise IntegrationError(
                f"«{manifest.name}» no está vinculada. Vincúlala en Aplicaciones vinculadas para autorizar el uso."
            )
        if link.status is CapabilityStatus.INCOMPATIBLE:
            raise IntegrationError(f"«{manifest.name}» no ofrece una interfaz pública que LEYRA pueda usar.")
        missing = set(link.missing_permissions)
        needed = set(manifest.permissions)
        if needed - set(link.granted_permissions) and needed & missing:
            raise IntegrationError(
                f"Faltan permisos autorizados para «{manifest.name}»: {', '.join(sorted(missing))}."
            )

    def _pick_action(self, manifest: ConnectorManifest, kinds: Iterable[ActionKind]) -> ConnectorAction:
        allowed = set(kinds)
        for action in manifest.actions:
            if action.kind in allowed:
                return action
        raise IntegrationError(f"«{manifest.name}» no expone ninguna acción compatible con esta solicitud.")

    def _step(self, manifest: ConnectorManifest, action: ConnectorAction, arguments: dict[str, Any]) -> ActionStep:
        arguments = action.validate_arguments(arguments)
        needs_confirmation = self.policy.needs_confirmation(action.kind.value, destructive=action.destructive)
        reason = ""
        if needs_confirmation:
            reason = "La operación envía datos fuera de LEYRA; requiere tu confirmación explícita."
        return ActionStep(
            connector_id=manifest.id,
            package_name=manifest.package_name,
            action_id=action.id,
            action_label=action.label,
            arguments=arguments,
            requires_confirmation=needs_confirmation,
            reason=reason,
        )

    def _plan_open(self, instruction: str, target: str) -> IntegrationPlan:
        package, manifest = self._resolve_target(target)
        action = self._pick_action(manifest, [ActionKind.LAUNCH, ActionKind.DEEP_LINK])
        self._require_linked(manifest)
        step = self._step(manifest, action, {})
        return IntegrationPlan(instruction=instruction, steps=(step,))

    def _plan_open_link(self, instruction: str, url: str, target: str | None) -> IntegrationPlan:
        if target:
            _, manifest = self._resolve_target(target)
        else:
            manifest = self._manifest_for_link(url)
        action = self._pick_action(manifest, [ActionKind.APP_LINK, ActionKind.DEEP_LINK])
        self._require_linked(manifest)
        parameter = action.parameters[0].name if action.parameters else "url"
        step = self._step(manifest, action, {parameter: url})
        return IntegrationPlan(instruction=instruction, steps=(step,))

    def _manifest_for_link(self, url: str) -> ConnectorManifest:
        host = re.sub(r"^https?://", "", url).split("/")[0].lower()
        for manifest in self.registry.manifests():
            if host.endswith(normalize(manifest.package_name)) or normalize(manifest.name).replace(" ", "") in host:
                return manifest
        raise IntegrationError(
            f"Ninguna aplicación vinculada declara manejar enlaces de {host}. Indica la aplicación de destino."
        )

    def _plan_share(self, instruction: str, kind: str, payload: str, target: str) -> IntegrationPlan:
        _, manifest = self._resolve_target(target)
        action = self._pick_action(manifest, [ActionKind.SHARE, ActionKind.INTENT])
        self._require_linked(manifest)
        names = {p.name: p for p in action.parameters}
        payload_name = next((n for n in ("text", "content", "body", "message") if n in names), None)
        file_name = next((n for n in ("file", "uri", "path", "attachment") if n in names), None)
        cleaned = payload.strip().strip("«»\"").strip()

        if kind in {"archivo", "documento", "imagen", "foto"}:
            if file_name is None:
                raise IntegrationError(f"«{manifest.name}» no acepta archivos mediante su acción pública.")
            raise IntegrationError(
                "Para compartir un archivo, adjúntalo primero en la conversación: LEYRA debe recibir el "
                "contenido antes de planificar el envío."
            )
        if kind == "enlace" or kind == "link":
            if payload_name is None and file_name is None:
                raise IntegrationError(f"«{manifest.name}» no acepta un enlace en su acción de compartir.")
            if not re.fullmatch(r"https?://\S+", cleaned):
                raise IntegrationError("Indica el enlace completo (https://…) que quieres compartir.")
            parameter = payload_name or file_name
            step = self._step(manifest, action, {parameter: cleaned})
            return IntegrationPlan(instruction=instruction, steps=(step,))

        if not cleaned:
            raise IntegrationError(
                "Indica el texto exacto a compartir, por ejemplo: «comparte el texto Hola, te envío el "
                f"informe con {manifest.name}»."
            )
        if payload_name is None:
            raise IntegrationError(f"«{manifest.name}» no acepta texto en su acción de compartir.")
        step = self._step(manifest, action, {payload_name: cleaned})
        return IntegrationPlan(instruction=instruction, steps=(step,))

    # -- execution ---------------------------------------------------------
    def execute(self, plan: IntegrationPlan, *, confirmed: bool = False) -> list[ExecutionResult]:
        """Dispatch a plan. ``confirmed`` only answers this single call."""
        if not plan.steps:
            return []
        if len(plan.steps) > self.policy.max_steps_per_plan:
            raise IntegrationError("El plan supera el máximo de pasos permitido por la política.")
        if not isinstance(confirmed, bool):
            raise IntegrationError("confirmed debe ser booleano explícito.")

        results: list[ExecutionResult] = []
        for step in plan.steps:
            if step.requires_confirmation and not confirmed:
                results.append(ExecutionResult(
                    status=ExecutionStatus.CONFIRMATION_REQUIRED,
                    connector_id=step.connector_id,
                    action_id=step.action_id,
                    detail=step.reason or "Esta acción requiere confirmación explícita.",
                ))
                self.registry.record("confirm_required", step.package_name, step.action_label)
                break
            link = self.registry.linked_app(step.package_name)
            if link is None or not link.enabled:
                results.append(ExecutionResult(
                    status=ExecutionStatus.DENIED,
                    connector_id=step.connector_id,
                    action_id=step.action_id,
                    detail="La aplicación no está vinculada o está desactivada.",
                ))
                break
            try:
                self.policy.check_package(step.package_name)
                self.policy.check_level(link.level)
            except IntegrationError as exc:
                results.append(ExecutionResult(
                    status=ExecutionStatus.DENIED,
                    connector_id=step.connector_id,
                    action_id=step.action_id,
                    detail=str(exc)[:200],
                ))
                break
            if not self.bridge.available():
                result = self.bridge.dispatch(step)
            else:
                try:
                    result = self.bridge.dispatch(step)
                except IntegrationError as exc:
                    result = ExecutionResult(
                        status=ExecutionStatus.FAILED,
                        connector_id=step.connector_id,
                        action_id=step.action_id,
                        detail=str(exc)[:200],
                    )
                except Exception:  # pragma: no cover - defensive: never leak internals
                    result = ExecutionResult(
                        status=ExecutionStatus.FAILED,
                        connector_id=step.connector_id,
                        action_id=step.action_id,
                        detail="El puente Android falló al despachar la acción.",
                    )
            results.append(result)
            self.registry.record(
                "execute" if result.status is ExecutionStatus.OK else "execute_failed",
                step.package_name,
                f"{step.action_label}: {result.status.value}",
            )
            if result.status is not ExecutionStatus.OK:
                if result.status is ExecutionStatus.FAILED:
                    self.registry.mark_error(step.package_name, result.detail)
                break
        return results

    def describe(self, instruction: str) -> dict[str, Any]:
        """Resolve an instruction and return a JSON-friendly preview."""
        plan = self.resolve(instruction)
        notes = list(plan.notes)
        payload: dict[str, Any] = {
            "plan": plan.to_dict(),
            "bridge": {"name": self.bridge.name, "available": self.bridge.available()},
        }
        if notes and notes[0].startswith("__capabilities__:"):
            payload["capabilities"] = self.find_capabilities(notes[0].split(":", 1)[1])
            payload["plan"]["notes"] = []
        elif notes and notes[0] == "__list_linked__":
            payload["linked"] = [link.to_dict() for link in self.registry.linked()]
            payload["plan"]["notes"] = []
        return payload

    def health(self) -> dict[str, Any]:
        bridge_ok = self.bridge.available()
        manifests = self.registry.manifests()
        return {
            "module": "app-integration",
            "status": "ok" if bridge_ok else "degraded",
            "bridge": {"name": self.bridge.name, "available": bridge_ok},
            "discovered": len(self.registry.discovered()),
            "connectors": len(manifests),
            "linked": len([link for link in self.registry.linked() if link.enabled]),
            "policy": self.policy.to_dict(),
            "detail": (
                "Puente Android conectado."
                if bridge_ok
                else "Sin puente Android: el módulo planifica pero no ejecuta en este entorno."
            ),
        }
