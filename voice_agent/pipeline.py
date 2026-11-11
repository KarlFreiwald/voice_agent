"""Framework-independent orchestration and bounded conversation history."""

from dataclasses import dataclass, field
from time import perf_counter
from typing import Callable

from .config import Settings
from .providers import Cartesia, Deepgram, Demo, LanguageModel, OpenAIText, ProviderError, Synthesizer, Transcriber


@dataclass
class Turn:
    transcript: str = ""
    response: str = ""
    audio: bytes = b""
    timings: dict = field(default_factory=dict)
    usage: dict = field(default_factory=dict)
    error: str = ""


class Pipeline:
    def __init__(self, settings: Settings, stt: Transcriber, llm: LanguageModel, tts: Synthesizer):
        self.settings, self.stt, self.llm, self.tts = settings, stt, llm, tts
        self.history: list[dict] = []

    def reset(self):
        self.history.clear()

    def run(self, *, audio: bytes | None = None, text: str | None = None,
            event: Callable[[str, dict], None] = lambda *_: None) -> Turn:
        turn = Turn()
        stage = "input"
        started = perf_counter()
        stage_started = started
        try:
            if (audio is None) == (text is None):
                raise ProviderError("Supply exactly one recording or text message.")
            if audio is not None:
                stage = "transcription"
                event("stage", {"name": stage})
                stage_started = perf_counter()
                result = self.stt.transcribe(audio)
                turn.transcript = result.text.strip()
                turn.usage[stage] = result.usage
                turn.timings[stage] = perf_counter() - stage_started
            else:
                turn.transcript = text.strip()
            if not turn.transcript:
                raise ProviderError("No speech or text detected. Please try again.")
            if len(turn.transcript) > 12000:
                raise ProviderError("Input is too long; keep each message below 12,000 characters.")
            event("transcript", {"text": turn.transcript})
            stage = "language_model"
            event("stage", {"name": stage})
            stage_started = perf_counter()
            user = {"role": "user", "content": turn.transcript}
            result = self.llm.respond(self.history + [user])
            turn.response = result.text
            turn.usage[stage] = result.usage
            turn.timings[stage] = perf_counter() - stage_started
            # Commit a completed text exchange even if speech generation later fails.
            self.history.extend([user, {"role": "assistant", "content": turn.response}])
            self.history = self.history[-2 * self.settings.history_turns:]
            event("response", {"text": turn.response})
            stage = "synthesis"
            event("stage", {"name": stage})
            stage_started = perf_counter()
            turn.audio = self.tts.synthesize(turn.response)
            turn.timings[stage] = perf_counter() - stage_started
            turn.usage[stage] = {"characters": len(turn.response)}
        except ProviderError as exc:
            turn.timings.setdefault(stage, perf_counter() - stage_started)
            turn.error = f"{stage}: {exc}"
        finally:
            turn.timings["total"] = perf_counter() - started
        return turn


def build_pipeline(settings: Settings, demo: bool = False) -> Pipeline:
    if demo:
        provider = Demo()
        return Pipeline(settings, provider, provider, provider)
    return Pipeline(settings, Deepgram(settings), OpenAIText(settings), Cartesia(settings))
