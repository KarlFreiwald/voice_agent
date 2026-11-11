# Voice Agent

A Python desktop voice chatbot for Windows 11 x64, with independently inspectable and replaceable stages:

```text
Microphone → Deepgram Nova-3 → OpenAI text model → Cartesia Sonic → Speakers
                  transcript       response            WAV audio
```

Initial defaults: English, GPT-6 Luna, and Sonic-3.6. Models, voice and language are configurable. Account availability and live API compatibility still need verification.

## Windows setup

Requires 64-bit Python 3.11 or newer and internet access for installation and live APIs. Backend tests were run with Python 3.14.8.

In PowerShell, from this directory:

```powershell
.\scripts\setup.ps1
.\scripts\run.ps1 -Demo
```

Demo mode makes **no API calls**. Transcripts and answers are simulated; playback is a short tone. Use it to check microphone capture, replay, the interface, and conversation flow before adding keys.

If PowerShell prevents running scripts, use these commands instead:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[build]"
# Copy only if config.local.json does not already exist:
Copy-Item config.example.json config.local.json
.\.venv\Scripts\python.exe -m voice_agent --demo
```

The setup script preserves existing configuration. Virtual environment activation is unnecessary.

## Live configuration

Edit the three API key fields in `config.local.json`, which is ignored by Git. Never put real keys in `config.example.json`.

- [Deepgram console](https://console.deepgram.com/): transcription key.
- [OpenAI API keys](https://platform.openai.com/api-keys): text-model key and API billing.
- [Cartesia keys](https://play.cartesia.ai/keys): standard API key for speech synthesis. Choose a voice available to your account.

Environment variables `DEEPGRAM_API_KEY`, `OPENAI_API_KEY`, and `CARTESIA_API_KEY` override file values. Restart after configuration changes, then run:

```powershell
.\scripts\run.ps1
# Or, without scripts:
.\.venv\Scripts\python.exe -m voice_agent
```

The default config location is the project directory, or beside the executable when packaged. Use `--config PATH` to override it.

## Desktop controls

1. Select a microphone. Refresh devices after attaching a new one.
2. Click **Record**, speak, then **Stop and send**. The default recording limit is 60 seconds; reaching it automatically sends the recording.
3. Inspect the transcript, answer, timings, model settings, and usage in the side panel.
4. Use **Replay recording**, **Replay reply**, and **Stop playback**. Starting a recording stops playback.
5. Type a message to bypass transcription.
6. **New conversation** clears history, displayed text, and retained audio.

The app uses Windows' default output device. Enable desktop microphone access under Windows Settings → Privacy & security → Microphone. Only one turn is processed at a time, on a background thread. Wait for the turn to finish before closing; network-request cancellation is not implemented.

If synthesis fails, the text answer and completed exchange remain available. Failed transcription or text generation does not add a partial exchange to history. **Speak replies** controls automatic playback; speech is still generated for replay.

## Test stages separately

The CLI and backend do not require PySide6. Each live command calls only its named provider. Add `--demo` before the subcommand to use fake providers.

```powershell
# Transcribe a 16-bit PCM WAV within the recording duration limit:
.\.venv\Scripts\python.exe -m voice_agent transcribe recordings\sample.wav

# Test the text model without either speech stage:
.\.venv\Scripts\python.exe -m voice_agent chat "Explain why the sky is blue in two sentences."

# Generate speech without the text model; explicitly saves a file:
.\.venv\Scripts\python.exe -m voice_agent speak "Hello, Karl." --output recordings\hello.wav

# Free CLI demo:
.\.venv\Scripts\python.exe -m voice_agent --demo chat "Hello"
```

CLI chat is a single exchange. The desktop pipeline maintains conversation history. Speech output refuses to overwrite an existing file.

## Costs, data, and languages

- Usage figures are measurements, not monetary quotes or a hard spending cap. Provider billing is authoritative.
- Defaults: 60-second recordings, six history exchanges, and 800 output tokens including reasoning. Typed messages are limited to 12,000 characters.
- The output-token limit can yield an incomplete response; its status is shown in the inspector. Increase the limit if necessary.
- Requests use a configurable socket timeout and no automatic retries. A timeout does not guarantee that the provider did not process or bill a request.
- Audio and conversations are held in memory locally; nothing is automatically saved. CLI `speak --output` is an explicit exception.
- Live mode sends audio to Deepgram, text/history to OpenAI, and response text to Cartesia. OpenAI requests use `store=false`; that is not a promise about all provider retention policies.
- This personal desktop app uses your own locally supplied keys. Do not distribute `config.local.json` or embed keys in source code or executables.
- For German later, change `language`, `response_language`, and choose compatible models/voice. Recognition and pronunciation still need per-language testing. The interface is currently English.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q voice_agent desktop.py
```

Tests cover request payloads, valid audio, stage ordering, bounded history, partial failures, and credential handling using fake providers and mocked HTTP. They do not verify actual provider accounts, GUI behavior, or audio hardware.

Manual checks after installation:

- Start demo mode; send text, record audio, and replay both the recording and tone.
- Start live mode; ask a short question and a follow-up requiring context.
- Stop playback, reset history, and try a disconnected microphone.
- Confirm invalid/missing keys produce readable errors without freezing the UI.
- Check model/voice access and provider usage dashboards.

## Windows executable

```powershell
.\scripts\build.ps1
```

The build script runs backend tests and packages with PyInstaller into `dist/VoiceAgent/VoiceAgent.exe`. Keep the whole `VoiceAgent` folder together. Create `config.local.json` beside the executable from the included template and add your keys locally. Create a Windows shortcut to launch it.

Dependency downloads were blocked in the restricted development session, so the GUI, microphone/speaker integration, packaging, and live APIs remain unverified. No executable has been produced yet.

## Code map

| Module | Responsibility |
| --- | --- |
| `config.py` | Local settings, environment keys, validation |
| `providers.py` | Independent STT, LLM, TTS adapters and fake providers |
| `pipeline.py` | Turn orchestration, history, timings, partial failures |
| `audio.py` | In-memory Qt microphone capture and playback |
| `ui.py` | Desktop interface and background worker |
| `__main__.py` | Launcher and individual-stage CLI |

## References

API payloads follow documentation checked November 11, 2026:

- [Deepgram prerecorded transcription](https://developers.deepgram.com/reference/speech-to-text/listen-pre-recorded)
- [OpenAI Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create)
- [Cartesia speech synthesis](https://docs.cartesia.ai/api-reference/tts/bytes)
- [Cartesia API versioning](https://docs.cartesia.ai/use-the-api/api-conventions)
- [Qt for Python](https://doc.qt.io/qtforpython-6/)
