import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from voice_agent.__main__ import main


class CliTests(unittest.TestCase):
    def test_demo_stages_and_overwrite_protection(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "demo.wav"
            config = Path(folder) / "missing.json"
            options = ["--config", str(config), "--demo"]
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(options + ["chat", "Hello"]), 0)
                self.assertEqual(main(options + ["speak", "Hello", "--output", str(path)]), 0)
                original = path.read_bytes()
                self.assertEqual(main(options + ["transcribe", str(path)]), 0)
                self.assertEqual(main(options + ["speak", "Hello", "--output", str(path)]), 1)
                self.assertEqual(path.read_bytes(), original)

    def test_missing_key_is_nonzero_without_network(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict("os.environ", {}, clear=True), patch("voice_agent.providers.urlopen") as network:
                with contextlib.redirect_stderr(io.StringIO()) as output:
                    result = main(["--config", str(Path(folder) / "missing.json"), "chat", "Hi"])
                self.assertEqual(result, 1)
                self.assertIn("OPENAI_API_KEY", output.getvalue())
                network.assert_not_called()


if __name__ == "__main__":
    unittest.main()
