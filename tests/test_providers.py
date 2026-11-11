import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from voice_agent.config import Settings
from voice_agent.providers import (Cartesia, Deepgram, Demo, OpenAIText, ProviderError,
                                   request, wav_info)


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(deepgram_api_key="secret", openai_api_key="secret", cartesia_api_key="secret")

    @patch("voice_agent.providers.request")
    def test_transcription_contract(self, send):
        send.return_value = json.dumps({"results": {"channels": [{"alternatives": [{"transcript": "Hello"}]}]}}).encode()
        result = Deepgram(self.settings).transcribe(Demo().synthesize("test"))
        self.assertEqual(result.text, "Hello")
        self.assertIn("model=nova-3", send.call_args.args[0])
        self.assertEqual(send.call_args.args[1]["Content-Type"], "audio/wav")

    @patch("voice_agent.providers.request")
    def test_response_contract_and_usage(self, send):
        send.return_value = json.dumps({"status": "completed", "output": [
            {"type": "reasoning"}, {"type": "message", "content": [{"type": "output_text", "text": "Hello"}]}],
            "usage": {"input_tokens": 20, "output_tokens": 4}}).encode()
        result = OpenAIText(self.settings).respond([{"role": "user", "content": "Hi"}])
        self.assertEqual(result.text, "Hello")
        self.assertEqual(result.usage["output_tokens"], 4)
        body = json.loads(send.call_args.args[2])
        self.assertFalse(body["store"])
        self.assertEqual(body["max_output_tokens"], 800)

    @patch("voice_agent.providers.request", return_value=b'{"status":"incomplete","output":[]}')
    def test_no_visible_output_is_actionable_error(self, send):
        with self.assertRaisesRegex(ProviderError, "max_output_tokens"):
            OpenAIText(self.settings).respond([])

    @patch("voice_agent.providers.request")
    def test_tts_contract_and_audio_validation(self, send):
        send.return_value = Demo().synthesize("test")
        audio = Cartesia(self.settings).synthesize("Hello")
        wav_info(audio)
        body = json.loads(send.call_args.args[2])
        self.assertEqual(body["voice"], self.settings.voice_id)
        self.assertEqual(body["output_format"]["encoding"], "pcm_s16le")
        send.return_value = b"not audio"
        with self.assertRaises(ProviderError):
            Cartesia(self.settings).synthesize("Hello")

    @patch("voice_agent.providers.request")
    def test_missing_key_never_sends_request(self, send):
        with self.assertRaisesRegex(ProviderError, "OPENAI_API_KEY"):
            OpenAIText(Settings()).respond([])
        send.assert_not_called()

    @patch("voice_agent.providers.urlopen")
    def test_http_failure_is_redacted_and_not_retried(self, open_url):
        open_url.side_effect = HTTPError("https://example.com", 401, "secret", {}, io.BytesIO(b"secret"))
        with self.assertRaises(ProviderError) as caught:
            request("https://example.com", {}, b"", 1)
        self.assertNotIn("secret", str(caught.exception))
        self.assertIn("401", str(caught.exception))
        self.assertEqual(open_url.call_count, 1)

    @patch("voice_agent.providers.urlopen", side_effect=URLError("secret"))
    def test_network_failure_is_redacted(self, open_url):
        with self.assertRaisesRegex(ProviderError, "connection failed"):
            request("https://example.com", {}, b"", 1)


if __name__ == "__main__":
    unittest.main()
