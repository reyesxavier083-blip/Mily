"""Voice engine settings and text preparation shared by web and Android.

Synthesis and recognition happen in the client (Web Speech API, Android
TextToSpeech / SpeechRecognizer, or a configured cloud provider). This module
owns the parts that must behave identically everywhere: validated settings,
sentence-aware chunking for low-latency progressive playback, expressive pauses
and duration estimation.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

LANGUAGES = {"es", "es-MX", "es-ES", "en", "en-US", "en-GB", "pt", "fr", "de", "it"}
STYLES = {"calida", "neutral", "profesional", "energica", "calma"}


class VoiceError(ValueError):
    """Invalid voice configuration."""


@dataclass(frozen=True)
class VoiceSettings:
    """User-tunable speech configuration with hard bounds."""

    voice_name: str = "LEYRA"
    voice_id: str = ""
    language: str = "es-MX"
    rate: float = 1.0
    pitch: float = 1.0
    volume: float = 1.0
    style: str = "calida"
    expressive_pauses: bool = True
    auto_speak: bool = False
    barge_in: bool = True

    def __post_init__(self) -> None:
        if not str(self.voice_name).strip() or len(self.voice_name) > 40:
            raise VoiceError("El nombre de voz debe tener entre 1 y 40 caracteres.")
        if self.language not in LANGUAGES:
            raise VoiceError(f"Idioma no soportado: {self.language}")
        for flag in ("rate", "pitch", "volume"):
            value = getattr(self, flag)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise VoiceError(f"{flag} debe ser numérico.")
        if not 0.5 <= float(self.rate) <= 2.0:
            raise VoiceError("La velocidad debe estar entre 0.5 y 2.0.")
        if not 0.0 <= float(self.pitch) <= 2.0:
            raise VoiceError("El tono debe estar entre 0.0 y 2.0.")
        if not 0.0 <= float(self.volume) <= 1.0:
            raise VoiceError("El volumen debe estar entre 0.0 y 1.0.")
        if self.style not in STYLES:
            raise VoiceError(f"Estilo no soportado: {self.style}")
        for flag in ("expressive_pauses", "auto_speak", "barge_in"):
            if type(getattr(self, flag)) is not bool:
                raise VoiceError(f"{flag} debe ser booleano.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "voiceName": self.voice_name,
            "voiceId": self.voice_id,
            "language": self.language,
            "rate": self.rate,
            "pitch": self.pitch,
            "volume": self.volume,
            "style": self.style,
            "expressivePauses": self.expressive_pauses,
            "autoSpeak": self.auto_speak,
            "bargeIn": self.barge_in,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "VoiceSettings":
        mapping = {
            "voiceName": "voice_name",
            "voiceId": "voice_id",
            "language": "language",
            "rate": "rate",
            "pitch": "pitch",
            "volume": "volume",
            "style": "style",
            "expressivePauses": "expressive_pauses",
            "autoSpeak": "auto_speak",
            "bargeIn": "barge_in",
        }
        kwargs = {mapping[key]: value for key, value in payload.items() if key in mapping}
        return cls(**kwargs)


_PAUSE = {".": 0.34, "?": 0.34, "!": 0.3, ":": 0.22, ";": 0.22, ",": 0.14}


def expressive_text(text: str, settings: VoiceSettings) -> str:
    """Insert natural pauses at sentence boundaries without altering words.

    Used for providers that accept punctuation as prosody. The original text is
    never reworded: only whitespace and punctuation spacing change.
    """
    clean = re.sub(r"[ \t]+", " ", str(text)).strip()
    if not clean:
        return ""
    if settings.expressive_pauses:
        clean = re.sub(r"\s*([.!?:;])\s*", r"\1 ", clean)
        clean = re.sub(r"([!?])\1+", r"\1", clean)
        clean = re.sub(r"\.{4,}", "…", clean)
    if settings.style == "calma":
        clean = re.sub(r"\s*([,;:])\s*", r"\1  ", clean)
    return clean


def chunk_text(text: str, *, max_chars: int = 240) -> list[str]:
    """Split text into speakable chunks at sentence boundaries (streaming TTS)."""
    if max_chars < 60:
        raise VoiceError("max_chars debe ser al menos 60.")
    clean = re.sub(r"\s+", " ", str(text)).strip()
    if not clean:
        return []
    sentences = re.split(r"(?<=[.!?…])\s+", clean)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        while len(sentence) > max_chars:
            cut = sentence.rfind(" ", 0, max_chars)
            cut = cut if cut > 40 else max_chars
            if current:
                chunks.append(current)
                current = ""
            chunks.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if not sentence:
            continue
        if len(current) + len(sentence) + 1 <= max_chars:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return [chunk for chunk in chunks if chunk]


def estimate_seconds(text: str, settings: VoiceSettings) -> float:
    """Approximate spoken duration, used to size the UI waveform."""
    words = len(str(text).split())
    base = words / (2.6 * max(0.5, float(settings.rate)))
    pauses = sum(str(text).count(char) for char in ".!?") * 0.3 if settings.expressive_pauses else 0.0
    return round(base + pauses, 1)


DEFAULT_SETTINGS = VoiceSettings()


def load_settings(store: Any, key: str = "voice") -> VoiceSettings:
    """Read voice settings from a ``Store``-like object, falling back safely."""
    payload = store.get_setting(key, None)
    if not isinstance(payload, dict):
        return DEFAULT_SETTINGS
    try:
        return VoiceSettings.from_dict(payload)
    except (VoiceError, TypeError):
        return DEFAULT_SETTINGS
