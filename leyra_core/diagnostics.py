"""Diagnostics hub: reports only what has actually been verified.

A module is ``ok`` only when its own check passed. Missing credentials, an
unavailable bridge or a missing dependency downgrade the report instead of being
hidden behind a green label.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Callable, Iterable, Mapping


class Health(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


_SEVERITY = {Health.OK: 0, Health.DEGRADED: 1, Health.UNAVAILABLE: 2, Health.ERROR: 3}


@dataclass(frozen=True)
class ModuleHealth:
    module: str
    status: Health
    detail: str = ""
    data: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"module": self.module, "status": self.status.value, "detail": self.detail, "data": dict(self.data)}


Checker = Callable[[], ModuleHealth]


class DiagnosticsHub:
    """Runs every registered checker and aggregates the real result."""

    def __init__(self, *, clock=time.time) -> None:
        self._checkers: dict[str, Checker] = {}
        self._clock = clock

    def register(self, name: str, checker: Checker) -> None:
        self._checkers[name] = checker

    def register_engine(self, name: str, engine: Any) -> None:
        """Register an object exposing ``health()`` returning a mapping."""
        def checker() -> ModuleHealth:
            try:
                payload = engine.health()
            except Exception:
                return ModuleHealth(name, Health.ERROR, "El módulo no respondió a su comprobación.")
            status = payload.get("status", "unavailable")
            return ModuleHealth(name, Health(status), str(payload.get("detail", "")), payload)
        self.register(name, checker)

    def run(self) -> dict[str, Any]:
        results: list[ModuleHealth] = []
        for name, checker in self._checkers.items():
            started = time.perf_counter()
            try:
                results.append(checker())
            except Exception:
                results.append(ModuleHealth(name, Health.ERROR, "La comprobación lanzó un error."))
            results[-1] = ModuleHealth(results[-1].module, results[-1].status, results[-1].detail,
                                       {**dict(results[-1].data), "durationMs": round((time.perf_counter() - started) * 1000, 1)})
        worst = max((r.status for r in results), key=lambda s: _SEVERITY[s], default=Health.OK)
        return {
            "status": worst.value,
            "checkedAt": self._clock(),
            "modules": [result.to_dict() for result in results],
            "counts": {status.value: sum(1 for r in results if r.status is status) for status in Health},
        }


def aggregate(checks: Iterable[ModuleHealth]) -> dict[str, Any]:
    modules = [check.to_dict() for check in checks]
    worst = max((check.status for check in checks), key=lambda s: _SEVERITY[s], default=Health.OK)
    return {"status": worst.value, "modules": modules}


def static_check(name: str, ok: bool, detail: str, *, status_when_down: Health = Health.UNAVAILABLE,
                 data: Mapping[str, Any] | None = None) -> ModuleHealth:
    return ModuleHealth(name, Health.OK if ok else status_when_down, detail, data or {})
