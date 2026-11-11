"""Small synchronous HTTP adapters. The UI runs these on a worker thread."""

from dataclasses import dataclass, field
import io
import json
import math
import struct
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import wave

from .config import Settings


class ProviderError(RuntimeError):
    pass


@dataclass
class TextResult:
    text: str
    usage: dict = field(default_factory=dict)


class Transcriber(Protocol):
    def transcribe(self, audio: bytes) -> TextResult: ...


class LanguageModel(Protocol):
    def respond(self, messages: list[dict]) -> TextResult: ...


class Synthesizer(Protocol):
    def synthesize(self, text: str) -> bytes: ...


def request(url: str, headers: dict, body: bytes, timeout: int) -> bytes:
    """One request, no automatic retries that could incur duplicate charges."""
    try:
        with urlopen(Request(url, data=body, headers=headers, method="POST"), timeout=timeout) as response:
            return response.read()
    except HTTPError as exc:
        # Do not expose response bodies: they can contain echoed keys or input text.
        code = exc.code
        exc.close()
        hints = {400: "Check the model, language, voice and request settings.",
                 401: "Check the API key.", 403: "Check account access and permissions.",
                 404: "Check model or voice availability.",
                 429: "Check credits and rate limits; try again later."}
        raise ProviderError(f"API returned HTTP {code}. " + hints.get(code, "Try again later; check provider status.")) from None
    except (URLError, TimeoutError, OSError):
        raise ProviderError("API connection failed or timed out. Check your connection. No automatic retry was made.") from None


def require_key(key: str, name: str):
    if not key.strip():
        raise ProviderError(f"Missing {name}. Set it in config.local.json or your environment, then restart.")


def json_result(raw: bytes) -> dict:
    try:
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except (ValueError, UnicodeError):
        raise ProviderError("Provider returned an invalid JSON response.") from None


def wav_info(audio: bytes) -> tuple[int, int, bytes]:
    try:
        with wave.open(io.BytesIO(audio), "rb") as wav:
            if wav.getsampwidth() != 2 or wav.getcomptype() != "NONE":
                raise ValueError()
            rate, channels = wav.getframerate(), wav.getnchannels()
            frames = wav.readframes(wav.getnframes())
            if not frames or rate <= 0 or channels not in (1, 2):
                raise ValueError()
            return rate, channels, frames
    except (wave.Error, EOFError, ValueError):
        raise ProviderError("Expected a nonempty 16-bit PCM WAV file (mono or stereo).") from None


def make_wav(pcm: bytes, rate: int, channels: int = 1) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return out.getvalue()


class Deepgram:
    def __init__(self, settings: Settings):
        self.s = settings

    def transcribe(self, audio: bytes) -> TextResult:
        require_key(self.s.deepgram_api_key, "DEEPGRAM_API_KEY")
        rate, channels, frames = wav_info(audio)
        query = urlencode({"model": self.s.stt_model, "language": self.s.language, "smart_format": "true"})
        result = json_result(request("https://api.deepgram.com/v1/listen?" + query,
            {"Authorization": "Token " + self.s.deepgram_api_key, "Content-Type": "audio/wav"},
            audio, self.s.timeout_seconds))
        try:
            text = result["results"]["channels"][0]["alternatives"][0]["transcript"]
            if not isinstance(text, str):
                raise TypeError()
        except (KeyError, IndexError, TypeError):
            raise ProviderError("Transcription response did not contain a transcript.") from None
        return TextResult(text.strip(), {"input_audio_seconds": round(len(frames) / (2 * channels * rate), 3)})


class OpenAIText:
    def __init__(self, settings: Settings):
        self.s = settings

    def respond(self, messages: list[dict]) -> TextResult:
        require_key(self.s.openai_api_key, "OPENAI_API_KEY")
        payload = {"model": self.s.llm_model, "input": messages, "store": False,
                   "instructions": f"You are a helpful conversational assistant. Reply in {self.s.response_language}. "
                                   "Keep answers brief, usually two or three sentences, and suitable for speaking aloud. "
                                   "Use plain text rather than Markdown unless asked otherwise.",
                   "max_output_tokens": self.s.max_output_tokens}
        result = json_result(request("https://api.openai.com/v1/responses",
            {"Authorization": "Bearer " + self.s.openai_api_key, "Content-Type": "application/json"},
            json.dumps(payload).encode(), self.s.timeout_seconds))
        try:
            text = "\n".join(part.get("text", part.get("refusal", ""))
                             for item in result.get("output", []) if item.get("type") == "message"
                             for part in item.get("content", [])
                             if part.get("type") in ("output_text", "refusal")).strip()
        except (AttributeError, TypeError):
            raise ProviderError("Text model returned an unexpected response format.") from None
        if not text:
            raise ProviderError("Text model returned no speakable text. Check model access or increase max_output_tokens.")
        usage = result.get("usage") or {}
        return TextResult(text, {"input_tokens": usage.get("input_tokens", 0),
                                 "output_tokens": usage.get("output_tokens", 0),
                                 "status": result.get("status", "unknown")})


class Cartesia:
    def __init__(self, settings: Settings):
        self.s = settings

    def synthesize(self, text: str) -> bytes:
        require_key(self.s.cartesia_api_key, "CARTESIA_API_KEY")
        payload = {"model_id": self.s.tts_model, "transcript": text,
                   "voice": self.s.voice_id, "language": self.s.language,
                   "output_format": {"container": "wav", "encoding": "pcm_s16le", "sample_rate": 44100}}
        audio = request("https://api.cartesia.ai/tts/bytes",
            {"Authorization": "Bearer " + self.s.cartesia_api_key,
             "Cartesia-Version": self.s.cartesia_version, "Content-Type": "application/json"},
            json.dumps(payload).encode(), self.s.timeout_seconds)
        wav_info(audio)
        return audio


class Demo:
    """Explicit fake responses plus a tone; never sends audio or text anywhere."""
    def transcribe(self, audio: bytes) -> TextResult:
        wav_info(audio)
        return TextResult("[Demo transcript] Hello! This is a microphone test.")

    def respond(self, messages: list[dict]) -> TextResult:
        return TextResult("This is a demo response, not an LLM answer. Your latest message was: " + messages[-1]["content"])

    def synthesize(self, text: str) -> bytes:
        rate = 24000
        pcm = b"".join(struct.pack("<h", int(1800 * math.sin(2 * math.pi * 440 * i / rate))) for i in range(rate // 4))
        return make_wav(pcm, rate)
