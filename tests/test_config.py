import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from voice_agent.config import Settings, load_settings


class ConfigTests(unittest.TestCase):
    def test_settings_repr_excludes_keys(self):
        self.assertNotIn("private-value", repr(Settings(openai_api_key="private-value")))

    def test_bounds_and_types(self):
        for value in (0, -1, True, "6", 21):
            with self.assertRaises(ValueError):
                Settings(history_turns=value)

    def test_environment_overrides_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            path.write_text(json.dumps({"openai_api_key": "file-key"}), encoding="utf-8")
            with patch.dict("os.environ", {"OPENAI_API_KEY": "env-key"}):
                self.assertEqual(load_settings(path).openai_api_key, "env-key")

    def test_invalid_file_does_not_echo_content(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            path.write_text('{"openai_api_key": "secret", broken}', encoding="utf-8")
            with self.assertRaises(ValueError) as caught:
                load_settings(path)
            self.assertNotIn("secret", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
