"""Launch the GUI, or exercise an individual pipeline stage from the terminal."""

import argparse
import json
from pathlib import Path
import sys

from .config import load_settings
from .pipeline import build_pipeline
from .providers import ProviderError, wav_info


def main(argv=None):
    parser = argparse.ArgumentParser(description="Inspectable desktop voice agent")
    parser.add_argument("--config", type=Path, help="Path to local JSON configuration")
    parser.add_argument("--demo", action="store_true", help="Fake responses and a test tone; no API calls")
    sub = parser.add_subparsers(dest="command")
    stt = sub.add_parser("transcribe", help="Transcribe a 16-bit PCM WAV file")
    stt.add_argument("file", type=Path)
    chat = sub.add_parser("chat", help="Test one text-model request without speech")
    chat.add_argument("text")
    tts = sub.add_parser("speak", help="Generate a WAV file without invoking the text model")
    tts.add_argument("text")
    tts.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        settings = load_settings(args.config)
        if args.command is None:
            from .ui import launch
            return launch(settings, args.demo)
        pipeline = build_pipeline(settings, args.demo)
        if args.command == "transcribe":
            if args.file.stat().st_size > 24 * 1024 * 1024:
                raise ValueError("Audio file exceeds the prototype's 24 MiB limit.")
            audio = args.file.read_bytes()
            rate, channels, pcm = wav_info(audio)
            if len(pcm) / (2 * channels * rate) > settings.max_recording_seconds:
                raise ValueError("Audio file exceeds max_recording_seconds.")
            result = pipeline.stt.transcribe(audio)
        elif args.command == "chat":
            if not args.text.strip() or len(args.text) > 12000:
                raise ValueError("Supply 1–12,000 characters of text.")
            result = pipeline.llm.respond([{"role": "user", "content": args.text}])
        else:
            if not args.text.strip() or len(args.text) > 12000:
                raise ValueError("Supply 1–12,000 characters of text.")
            if args.output.exists():
                raise ValueError("Output file already exists; choose a new filename.")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            audio = pipeline.tts.synthesize(args.text)
            args.output.write_bytes(audio)
            print(f"Wrote {args.output}")
            return 0
        print(json.dumps({"text": result.text, "usage": result.usage}, indent=2, ensure_ascii=False))
        return 0
    except (ProviderError, ValueError, OSError) as exc:
        if args.command is None:
            try:
                from PySide6.QtWidgets import QApplication, QMessageBox
                app = QApplication.instance() or QApplication([])
                QMessageBox.critical(None, "Voice Agent setup", str(exc))
            except ImportError:
                pass
        print(str(exc), file=sys.stderr)
        return 1
    except ImportError:
        print('Desktop dependencies are missing. Run: python -m pip install -e "."', file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
