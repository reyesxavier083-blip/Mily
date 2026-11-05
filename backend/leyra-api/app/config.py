"""Configuration for the LEYRA API. Secrets are read from the environment only."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Mapping


def _float(source: Mapping[str, str], key: str, default: float) -> float:
    try:
        return float(source.get(key, default))
    except (TypeError, ValueError):
        return default


def _int(source: Mapping[str, str], key: str, default: int) -> int:
    try:
        return int(source.get(key, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    app_name: str = "LEYRA IA"
    version: str = "1.0.0"
    api_token: str = ""
    allowed_origins: tuple[str, ...] = ()
    data_dir: Path = Path("data")
    web_dir: Path = Path("web")
    rate_limit_window: float = 60.0
    rate_limit_max: int = 120
    max_body_bytes: int = 8 * 1024 * 1024
    max_upload_bytes: int = 20 * 1024 * 1024
    default_model: str = ""
    temperature: float = 0.6
    max_output_tokens: int = 1200
    allow_local_only: bool = False

    @property
    def auth_required(self) -> bool:
        return bool(self.api_token)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None, *, root: Path | None = None) -> "Settings":
        source = env if env is not None else os.environ
        base = root or Path(__file__).resolve().parents[3]
        data = Path(source.get("LEYRA_DATA_DIR", base / "data"))
        web = Path(source.get("LEYRA_WEB_DIR", base / "web"))
        origins = tuple(
            origin.strip().rstrip("/")
            for origin in source.get("LEYRA_ALLOWED_ORIGINS", "").split(",")
            if origin.strip()
        )
        return cls(
            api_token=str(source.get("LEYRA_API_TOKEN", "")).strip(),
            allowed_origins=origins,
            data_dir=data,
            web_dir=web,
            rate_limit_window=max(1.0, _float(source, "LEYRA_RATE_WINDOW_SECONDS", 60.0)),
            rate_limit_max=max(1, _int(source, "LEYRA_RATE_MAX", 120)),
            max_body_bytes=max(1024, _int(source, "LEYRA_MAX_BODY_BYTES", 8 * 1024 * 1024)),
            max_upload_bytes=max(1024, _int(source, "LEYRA_MAX_UPLOAD_BYTES", 20 * 1024 * 1024)),
            default_model=str(source.get("LEYRA_DEFAULT_MODEL", "")).strip(),
            temperature=max(0.0, min(_float(source, "LEYRA_TEMPERATURE", 0.6), 2.0)),
            max_output_tokens=max(64, min(_int(source, "LEYRA_MAX_OUTPUT_TOKENS", 1200), 8000)),
        )


@dataclass
class RateLimiter:
    """Per-IP token bucket kept in memory. Replace with Redis when scaling out."""

    window: float
    maximum: int
    bucket: dict[str, tuple[float, int]] = field(default_factory=dict)

    def allow(self, key: str, *, now: float) -> bool:
        start, count = self.bucket.get(key, (now, 0))
        if now - start >= self.window:
            start, count = now, 0
        count += 1
        self.bucket[key] = (start, count)
        if len(self.bucket) > 5000:
            for item_key, (item_start, _) in list(self.bucket.items()):
                if now - item_start >= self.window:
                    self.bucket.pop(item_key, None)
        return count <= self.maximum
