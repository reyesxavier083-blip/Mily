"""LEYRA TOOLS ENGINE.

Every tool declares a typed input schema, a risk category, an availability check
and a real implementation. Tools that need a provider, a device capability or a
library that is not present report ``unavailable`` with the missing dependency
instead of returning invented data.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Iterable, Mapping

from mily_core.permission_manager import PermissionDecision, PermissionManager, ToolRisk


class ParamKind(str, Enum):
    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    TEXT = "text"
    JSON = "json"


class ToolStatus(str, Enum):
    OK = "ok"
    UNAVAILABLE = "unavailable"
    CONFIRMATION_REQUIRED = "confirmation_required"
    DENIED = "denied"
    INVALID = "invalid"
    FAILED = "failed"


class ToolError(ValueError):
    """Invalid tool invocation supplied by the caller."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ToolError(message)


@dataclass(frozen=True)
class ToolParameter:
    name: str
    kind: ParamKind
    description: str = ""
    required: bool = True
    default: Any = None
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] = ()

    def coerce(self, value: Any) -> Any:
        if value is None:
            _require(not self.required, f"El parámetro «{self.name}» es obligatorio.")
            return self.default
        if self.kind is ParamKind.BOOLEAN:
            if isinstance(value, bool):
                return value
            if isinstance(value, str) and value.lower() in {"true", "false"}:
                return value.lower() == "true"
            raise ToolError(f"«{self.name}» debe ser booleano.")
        if self.kind in (ParamKind.NUMBER, ParamKind.INTEGER):
            if isinstance(value, bool):
                raise ToolError(f"«{self.name}» debe ser numérico.")
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise ToolError(f"«{self.name}» debe ser numérico.") from exc
            if not math.isfinite(number):
                raise ToolError(f"«{self.name}» debe ser un número finito.")
            if self.kind is ParamKind.INTEGER:
                _require(number.is_integer(), f"«{self.name}» debe ser entero.")
                number = int(number)
            if self.minimum is not None and number < self.minimum:
                raise ToolError(f"«{self.name}» debe ser ≥ {self.minimum}.")
            if self.maximum is not None and number > self.maximum:
                raise ToolError(f"«{self.name}» debe ser ≤ {self.maximum}.")
            return number
        if self.kind is ParamKind.JSON:
            if isinstance(value, (dict, list)):
                return value
            try:
                return json.loads(str(value))
            except (TypeError, ValueError) as exc:
                raise ToolError(f"«{self.name}» debe ser JSON válido.") from exc
        text = value if isinstance(value, str) else str(value)
        _require(len(text) <= 8000, f"«{self.name}» supera el límite de tamaño.")
        if self.choices:
            _require(text in self.choices, f"«{self.name}» debe ser uno de: {', '.join(self.choices)}.")
        return text


@dataclass(frozen=True)
class ToolSpec:
    name: str
    title: str
    description: str
    risk: ToolRisk
    parameters: tuple[ToolParameter, ...] = ()
    requires: tuple[str, ...] = ()
    category: str = "general"

    def validate(self, arguments: Mapping[str, Any] | None) -> dict[str, Any]:
        provided = dict(arguments or {})
        known = {p.name for p in self.parameters}
        unknown = set(provided) - known
        _require(not unknown, f"Parámetros desconocidos para «{self.name}»: {', '.join(sorted(unknown))}.")
        normalized: dict[str, Any] = {}
        for parameter in self.parameters:
            if parameter.name in provided or parameter.required:
                normalized[parameter.name] = parameter.coerce(provided.get(parameter.name))
        return normalized

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "risk": self.risk.value,
            "category": self.category,
            "requires": list(self.requires),
            "parameters": [
                {
                    "name": p.name,
                    "kind": p.kind.value,
                    "description": p.description,
                    "required": p.required,
                    "default": p.default,
                    "minimum": p.minimum,
                    "maximum": p.maximum,
                    "choices": list(p.choices),
                }
                for p in self.parameters
            ],
        }


@dataclass(frozen=True)
class ToolResult:
    status: ToolStatus
    tool: str
    output: Any = None
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status is ToolStatus.OK

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status.value, "tool": self.tool, "output": self.output, "detail": self.detail}


Handler = Callable[[dict[str, Any]], Any]


@dataclass
class Tool:
    spec: ToolSpec
    handler: Handler | None = None
    availability: Callable[[], tuple[bool, str]] | None = None

    def available(self) -> tuple[bool, str]:
        if self.availability is not None:
            available, reason = self.availability()
            if not available:
                return False, reason
        if self.handler is None:
            return False, "La herramienta no tiene implementación en este entorno."
        return True, ""


class ToolRegistry:
    """Trusted registry. The allowlist for ``PermissionManager`` comes from here."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._permissions: PermissionManager | None = None

    def register(self, tool: Tool) -> Tool:
        if not isinstance(tool, Tool):
            raise ToolError("register() espera una Tool.")
        if tool.spec.name in self._tools:
            raise ToolError(f"Herramienta duplicada: {tool.spec.name}")
        self._tools[tool.spec.name] = tool
        self._permissions = None  # rebuild the allowlist lazily
        return tool

    def get(self, name: str) -> Tool:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolError(f"Herramienta desconocida: {name}")
        return tool

    def names(self) -> Iterable[str]:
        return tuple(self._tools)

    def list(self) -> list[dict[str, Any]]:
        entries = []
        for tool in self._tools.values():
            available, reason = tool.available()
            entry = tool.spec.to_dict()
            entry["available"] = available
            entry["unavailableReason"] = reason
            entries.append(entry)
        return sorted(entries, key=lambda item: (item["category"], item["title"].lower()))

    @property
    def permissions(self) -> PermissionManager:
        if self._permissions is None:
            self._permissions = PermissionManager({t.spec.name: t.spec.risk for t in self._tools.values()})
        return self._permissions

    def execute(self, name: str, arguments: Mapping[str, Any] | None, *, confirmed: bool = False) -> ToolResult:
        try:
            tool = self.get(name)
        except ToolError as exc:
            return ToolResult(ToolStatus.INVALID, name, detail=str(exc))
        try:
            normalized = tool.spec.validate(arguments)
        except ToolError as exc:
            return ToolResult(ToolStatus.INVALID, name, detail=str(exc))

        authorization = self.permissions.authorize(name, tool.spec.risk, confirmed=confirmed)
        if authorization.decision is PermissionDecision.DENY:
            return ToolResult(ToolStatus.DENIED, name, detail=authorization.reason)
        if authorization.decision is PermissionDecision.REQUIRE_CONFIRMATION:
            return ToolResult(ToolStatus.CONFIRMATION_REQUIRED, name, detail=authorization.reason)

        available, reason = tool.available()
        if not available:
            return ToolResult(ToolStatus.UNAVAILABLE, name, detail=reason)
        try:
            output = tool.handler(normalized)  # type: ignore[misc]
        except ToolError as exc:
            return ToolResult(ToolStatus.INVALID, name, detail=str(exc))
        except Exception:  # pragma: no cover - defensive: never leak internals
            return ToolResult(ToolStatus.FAILED, name, detail="La herramienta falló durante la ejecución.")
        return ToolResult(ToolStatus.OK, name, output=output)

    def health(self) -> dict[str, Any]:
        entries = self.list()
        ready = [item for item in entries if item["available"]]
        return {
            "module": "tools",
            "status": "ok" if ready else "unavailable",
            "total": len(entries),
            "available": len(ready),
            "unavailable": [item["name"] for item in entries if not item["available"]],
            "detail": f"{len(ready)} de {len(entries)} herramientas listas.",
        }


# ---------------------------------------------------------------------------
# Real tools
# ---------------------------------------------------------------------------

_ALLOWED_FUNCTIONS: dict[str, Any] = {
    "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "log": math.log, "log10": math.log10, "exp": math.exp, "floor": math.floor,
    "ceil": math.ceil, "abs": abs, "round": round, "pow": pow,
}
_CONSTANTS = {"pi": math.pi, "e": math.e, "tau": math.tau}


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _eval_node(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.FloorDiv)):
        left, right = _eval_node(node.left), _eval_node(node.right)
        if isinstance(node.op, ast.Div) and right == 0:
            raise ToolError("División entre cero.")
        if isinstance(node.op, ast.Pow) and abs(right) > 512:
            raise ToolError("Exponente fuera del rango permitido.")
        operation = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
                     ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b,
                     ast.Pow: lambda a, b: a ** b, ast.Mod: lambda a, b: a % b,
                     ast.FloorDiv: lambda a, b: a // b}[type(node.op)]
        result = operation(left, right)
        if not math.isfinite(result):
            raise ToolError("El resultado no es un número finito.")
        return float(result)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        function = _ALLOWED_FUNCTIONS.get(node.func.id)
        if function is None:
            raise ToolError(f"Función no permitida: {node.func.id}.")
        args = [_eval_node(arg) for arg in node.args]
        if len(args) > 3:
            raise ToolError("Demasiados argumentos.")
        if node.func.id == "round" and len(args) == 2:
            args[1] = int(args[1])
        try:
            return float(function(*args))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ToolError("Argumentos no válidos para la función.") from exc
    if isinstance(node, ast.Name) and node.id in _CONSTANTS:
        return float(_CONSTANTS[node.id])
    raise ToolError("La expresión contiene elementos no permitidos.")


def calculate(arguments: dict[str, Any]) -> dict[str, Any]:
    expression = str(arguments["expression"]).strip()
    _require(len(expression) <= 240, "La expresión es demasiado larga.")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ToolError("Expresión matemática inválida.") from exc
    value = _eval_node(tree)
    return {"expression": expression, "value": value}


def _conversions() -> dict[str, dict[str, float]]:
    return {
        "longitud": {"m": 1.0, "km": 1000.0, "cm": 0.01, "mm": 0.001, "mi": 1609.344, "ft": 0.3048, "in": 0.0254, "yd": 0.9144},
        "masa": {"kg": 1.0, "g": 0.001, "mg": 1e-6, "t": 1000.0, "lb": 0.45359237, "oz": 0.028349523125},
        "volumen": {"l": 1.0, "ml": 0.001, "m3": 1000.0, "gal": 3.785411784, "floz": 0.0295735},
        "datos": {"B": 1.0, "KB": 1e3, "MB": 1e6, "GB": 1e9, "TB": 1e12, "KiB": 1024.0, "MiB": 1048576.0, "GiB": 1073741824.0},
        "tiempo": {"s": 1.0, "min": 60.0, "h": 3600.0, "d": 86400.0, "semana": 604800.0},
        "area": {"m2": 1.0, "km2": 1e6, "cm2": 1e-4, "ha": 10000.0, "acre": 4046.8564224},
    }


def convert_units(arguments: dict[str, Any]) -> dict[str, Any]:
    category = str(arguments["category"]).lower()
    table = _conversions().get(category)
    if table is None:
        raise ToolError(f"Categoría no soportada: {category}")
    source, target = str(arguments["from"]), str(arguments["to"])
    if source not in table or target not in table:
        raise ToolError(f"Unidades disponibles en {category}: {', '.join(table)}.")
    value = float(arguments["value"])
    result = value * table[source] / table[target]
    return {"category": category, "value": value, "from": source, "to": target, "result": result}


def convert_temperature(arguments: dict[str, Any]) -> dict[str, Any]:
    source = str(arguments["from"]).upper()
    target = str(arguments["to"]).upper()
    value = float(arguments["value"])
    if source not in {"C", "F", "K"} or target not in {"C", "F", "K"}:
        raise ToolError("Unidades de temperatura válidas: C, F, K.")
    celsius = {"C": value, "F": (value - 32) * 5 / 9, "K": value - 273.15}[source]
    result = {"C": celsius, "F": celsius * 9 / 5 + 32, "K": celsius + 273.15}[target]
    return {"from": source, "to": target, "value": value, "result": round(result, 6)}


def current_time(arguments: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {"iso": now.isoformat(), "utc": now.strftime("%Y-%m-%d %H:%M:%S UTC"), "epoch": int(now.timestamp())}


def text_stats(arguments: dict[str, Any]) -> dict[str, Any]:
    text = str(arguments["text"])
    words = [word for word in text.split() if word.strip()]
    return {
        "characters": len(text),
        "charactersNoSpaces": len("".join(text.split())),
        "words": len(words),
        "lines": text.count("\n") + 1 if text else 0,
        "readingSeconds": round(len(words) / 3.5),
    }


def data_summary(arguments: dict[str, Any]) -> dict[str, Any]:
    values = arguments["values"]
    if not isinstance(values, list) or not values:
        raise ToolError("values debe ser una lista no vacía de números.")
    numbers: list[float] = []
    for item in values[:5000]:
        if isinstance(item, bool):
            raise ToolError("values solo admite números.")
        try:
            numbers.append(float(item))
        except (TypeError, ValueError) as exc:
            raise ToolError("values solo admite números.") from exc
    numbers.sort()
    count = len(numbers)
    total = sum(numbers)
    mean = total / count
    median = numbers[count // 2] if count % 2 else (numbers[count // 2 - 1] + numbers[count // 2]) / 2
    variance = sum((value - mean) ** 2 for value in numbers) / count
    return {
        "count": count, "sum": total, "mean": mean, "median": median,
        "min": numbers[0], "max": numbers[-1], "stdev": math.sqrt(variance),
        "histogram": _histogram(numbers),
    }


def _histogram(numbers: list[float], bins: int = 8) -> list[dict[str, Any]]:
    if len(set(numbers)) == 1:
        return [{"from": numbers[0], "to": numbers[0], "count": len(numbers)}]
    low, high = numbers[0], numbers[-1]
    width = (high - low) / bins
    buckets = [{"from": low + i * width, "to": low + (i + 1) * width, "count": 0} for i in range(bins)]
    for value in numbers:
        index = min(bins - 1, int((value - low) / width) if width else 0)
        buckets[index]["count"] += 1
    return buckets


def json_pretty(arguments: dict[str, Any]) -> dict[str, Any]:
    payload = arguments["data"]
    return {"formatted": json.dumps(payload, ensure_ascii=False, indent=2), "type": type(payload).__name__}


def _provider_tool(requirement: str) -> Callable[[], tuple[bool, str]]:
    def check() -> tuple[bool, str]:
        return False, requirement
    return check


def _pdf_available() -> tuple[bool, str]:
    if importlib.util.find_spec("pypdf") is None:
        return False, "Falta la dependencia pypdf en el servidor."
    return True, ""


def read_pdf(arguments: dict[str, Any]) -> dict[str, Any]:
    from pypdf import PdfReader  # imported lazily after the availability check

    path = str(arguments["path"])
    if not path.lower().endswith(".pdf"):
        raise ToolError("El archivo debe ser un PDF.")
    try:
        reader = PdfReader(path)
    except Exception as exc:  # pragma: no cover - depends on the file
        raise ToolError("No se pudo abrir el PDF.") from exc
    pages = min(len(reader.pages), 40)
    text = "\n\n".join((reader.pages[i].extract_text() or "") for i in range(pages))
    return {"pages": len(reader.pages), "extractedPages": pages, "text": text[:20000]}


def build_default_registry(*, web_search: Callable[[dict[str, Any]], Any] | None = None,
                           currency: Callable[[dict[str, Any]], Any] | None = None) -> ToolRegistry:
    """Register the toolset. Provider-backed tools stay unavailable without adapters."""
    registry = ToolRegistry()
    registry.register(Tool(
        spec=ToolSpec(
            name="calculator.expression",
            title="Calculadora",
            description="Evalúa una expresión matemática con funciones y constantes permitidas.",
            risk=ToolRisk.READ_ONLY,
            category="matemáticas",
            parameters=(ToolParameter("expression", ParamKind.STRING,
                                      "Expresión, por ejemplo: sqrt(2)*10 + log10(1000)", maximum=None),),
        ),
        handler=calculate,
    ))
    units = sorted(_conversions())
    registry.register(Tool(
        spec=ToolSpec(
            name="units.convert",
            title="Conversión de unidades",
            description="Convierte longitud, masa, volumen, datos, tiempo y área.",
            risk=ToolRisk.READ_ONLY,
            category="matemáticas",
            parameters=(
                ToolParameter("value", ParamKind.NUMBER, "Cantidad a convertir", minimum=-1e18, maximum=1e18),
                ToolParameter("from", ParamKind.STRING, "Unidad de origen"),
                ToolParameter("to", ParamKind.STRING, "Unidad de destino"),
                ToolParameter("category", ParamKind.STRING, "Familia de unidades", choices=tuple(units), default="longitud", required=False),
            ),
        ),
        handler=convert_units,
    ))
    registry.register(Tool(
        spec=ToolSpec(
            name="units.temperature",
            title="Temperatura",
            description="Convierte entre Celsius, Fahrenheit y Kelvin.",
            risk=ToolRisk.READ_ONLY,
            category="matemáticas",
            parameters=(
                ToolParameter("value", ParamKind.NUMBER, "Temperatura", minimum=-1e6, maximum=1e6),
                ToolParameter("from", ParamKind.STRING, "Unidad de origen", choices=("C", "F", "K")),
                ToolParameter("to", ParamKind.STRING, "Unidad de destino", choices=("C", "F", "K")),
            ),
        ),
        handler=convert_temperature,
    ))
    registry.register(Tool(
        spec=ToolSpec(
            name="time.now",
            title="Fecha y hora",
            description="Hora actual del servidor en UTC.",
            risk=ToolRisk.READ_ONLY,
            category="utilidades",
        ),
        handler=current_time,
    ))
    registry.register(Tool(
        spec=ToolSpec(
            name="text.stats",
            title="Estadísticas de texto",
            description="Cuenta caracteres, palabras, líneas y estima el tiempo de lectura.",
            risk=ToolRisk.READ_ONLY,
            category="utilidades",
            parameters=(ToolParameter("text", ParamKind.TEXT, "Texto a analizar"),),
        ),
        handler=text_stats,
    ))
    registry.register(Tool(
        spec=ToolSpec(
            name="data.summary",
            title="Análisis de datos",
            description="Estadística descriptiva e histograma de una lista de números.",
            risk=ToolRisk.READ_ONLY,
            category="datos",
            parameters=(ToolParameter("values", ParamKind.JSON, "Lista de números"),),
        ),
        handler=data_summary,
    ))
    registry.register(Tool(
        spec=ToolSpec(
            name="json.pretty",
            title="Formatear JSON",
            description="Valida y formatea JSON con sangría.",
            risk=ToolRisk.READ_ONLY,
            category="utilidades",
            parameters=(ToolParameter("data", ParamKind.JSON, "Datos JSON"),),
        ),
        handler=json_pretty,
    ))
    registry.register(Tool(
        spec=ToolSpec(
            name="pdf.read",
            title="Lectura de PDF",
            description="Extrae texto de las primeras 40 páginas de un PDF del servidor.",
            risk=ToolRisk.READ_ONLY,
            category="documentos",
            requires=("pypdf",),
            parameters=(ToolParameter("path", ParamKind.STRING, "Ruta del PDF dentro del almacenamiento de LEYRA"),),
        ),
        handler=read_pdf,
        availability=_pdf_available,
    ))
    registry.register(Tool(
        spec=ToolSpec(
            name="web.search",
            title="Búsqueda web",
            description="Busca en la web mediante el proveedor configurado.",
            risk=ToolRisk.EXTERNAL,
            category="investigación",
            requires=("proveedor de búsqueda",),
            parameters=(
                ToolParameter("query", ParamKind.STRING, "Consulta"),
                ToolParameter("count", ParamKind.INTEGER, "Resultados", default=5, required=False, minimum=1, maximum=10),
            ),
        ),
        handler=web_search,
        availability=None if web_search else _provider_tool("Configura un proveedor de búsqueda en el servidor."),
    ))
    registry.register(Tool(
        spec=ToolSpec(
            name="currency.convert",
            title="Conversión de monedas",
            description="Convierte monedas con tipos de cambio de un proveedor configurado.",
            risk=ToolRisk.READ_ONLY,
            category="finanzas",
            requires=("proveedor de tipos de cambio",),
            parameters=(
                ToolParameter("amount", ParamKind.NUMBER, "Importe", minimum=0, maximum=1e12),
                ToolParameter("from", ParamKind.STRING, "Moneda origen (ISO 4217)"),
                ToolParameter("to", ParamKind.STRING, "Moneda destino (ISO 4217)"),
            ),
        ),
        handler=currency,
        availability=None if currency else _provider_tool("Configura un proveedor de tipos de cambio en el servidor."),
    ))
    return registry
