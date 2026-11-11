"""Explicit local configuration. Never log the Settings object or API keys."""

from dataclasses import dataclass, field, fields
import json
import os
from pathlib import Path
import sys


@dataclass(frozen=True)
class Settings:
    deepgram_api_key: str = field(default="", repr=False)
    openai_api_key: str = field(default="", repr=False)
    cartesia_api_key: str = field(default="", repr=False)
    stt_model: str = "nova-3"
    llm_model: str = "gpt-6-luna"
    tts_model: str = "sonic-3.6"
    voice_id: str = "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4"
    cartesia_version: str = "2026-11-11"
    language: str = "en"
    response_language: str = "English"
    history_turns: int = 6
    max_output_tokens: int = 800
    max_recording_seconds: int = 60
    timeout_seconds: int = 30

    def __post_init__(self):
        limits = {"history_turns": (1, 20), "max_output_tokens": (64, 4000),
                  "max_recording_seconds": (1, 120), "timeout_seconds": (1, 120)}
        for item in fields(self):
            value = getattr(self, item.name)
            if item.name in limits:
                low, high = limits[item.name]
                if type(value) is not int or not low <= value <= high:
                    raise ValueError(f"{item.name} must be an integer from {low} to {high}.")
            elif not isinstance(value, str):
                raise ValueError(f"{item.name} must be a string.")
            elif not item.name.endswith("api_key") and not value.strip():
                raise ValueError(f"{item.name} cannot be empty.")


def default_path() -> Path:
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    return base / "config.local.json"


def load_settings(path: Path | None = None) -> Settings:
    path = path or default_path()
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (ValueError, OSError) as exc:
            raise ValueError(f"Cannot read configuration at {path}. Check JSON syntax.") from exc
        if not isinstance(data, dict):
            raise ValueError("Configuration must be a JSON object.")
        if set(data) - {item.name for item in fields(Settings)}:
            raise ValueError("Configuration contains unrecognized settings; compare config.example.json.")
    for name in ("deepgram_api_key", "openai_api_key", "cartesia_api_key"):
        if os.environ.get(name.upper()):
            data[name] = os.environ[name.upper()]
    return Settings(**data)
