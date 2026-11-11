import unittest
from unittest.mock import Mock

from voice_agent.config import Settings
from voice_agent.pipeline import Pipeline, build_pipeline
from voice_agent.providers import Demo, ProviderError, TextResult, wav_info


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.stt = Mock()
        self.stt.transcribe.return_value = TextResult("Hello")
        self.llm = Mock()
        self.llm.respond.return_value = TextResult("Hi", {"input_tokens": 12})
        self.tts = Mock()
        self.tts.synthesize.return_value = b"audio"
        self.pipeline = Pipeline(Settings(history_turns=2), self.stt, self.llm, self.tts)

    def test_full_turn_reports_stages_and_usage(self):
        events = []
        turn = self.pipeline.run(audio=b"input", event=lambda kind, data: events.append((kind, data)))
        self.assertFalse(turn.error)
        self.assertEqual(turn.audio, b"audio")
        self.assertEqual([data["name"] for kind, data in events if kind == "stage"],
                         ["transcription", "language_model", "synthesis"])
        self.assertEqual(turn.usage["language_model"]["input_tokens"], 12)

    def test_empty_transcription_never_calls_llm(self):
        self.stt.transcribe.return_value = TextResult("  ")
        self.assertIn("No speech", self.pipeline.run(audio=b"input").error)
        self.llm.respond.assert_not_called()
        self.tts.synthesize.assert_not_called()

    def test_text_bypasses_transcription(self):
        self.pipeline.run(text="Hello")
        self.stt.transcribe.assert_not_called()

    def test_tts_failure_preserves_response_and_history(self):
        self.tts.synthesize.side_effect = ProviderError("Quota exhausted")
        turn = self.pipeline.run(text="Hello")
        self.assertEqual(turn.response, "Hi")
        self.assertIn("synthesis", turn.error)
        self.assertEqual(len(self.pipeline.history), 2)

    def test_llm_failure_does_not_poison_history(self):
        self.llm.respond.side_effect = ProviderError("Timeout")
        self.assertTrue(self.pipeline.run(text="Hello").error)
        self.assertEqual(self.pipeline.history, [])
        self.tts.synthesize.assert_not_called()

    def test_history_is_bounded_and_resettable(self):
        for text in ("one", "two", "three"):
            self.pipeline.run(text=text)
        self.assertEqual(len(self.pipeline.history), 4)
        self.assertEqual(self.pipeline.history[0]["content"], "two")
        self.pipeline.reset()
        self.assertEqual(self.pipeline.history, [])

    def test_invalid_input_does_not_call_providers(self):
        for inputs in ({}, {"audio": b"a", "text": "b"}, {"text": "x" * 12001}):
            self.assertTrue(self.pipeline.run(**inputs).error)
        self.llm.respond.assert_not_called()

    def test_demo_produces_valid_audio_without_keys(self):
        pipeline = build_pipeline(Settings(), demo=True)
        turn = pipeline.run(audio=Demo().synthesize("test"))
        self.assertFalse(turn.error)
        self.assertIn("demo response", turn.response)
        rate, channels, frames = wav_info(turn.audio)
        self.assertEqual((rate, channels), (24000, 1))
        self.assertGreater(len(frames), 0)


if __name__ == "__main__":
    unittest.main()
