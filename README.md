# Voice Agent

A planned Python desktop voice chatbot for Windows 11 (x64), with independently inspectable and replaceable speech-to-text, text-model, and text-to-speech stages.

## Initial scope

- Python and PySide6 desktop interface.
- English conversation, with language configuration designed for later expansion.
- Click to record, then stop and send.
- Cloud API pipeline: Deepgram transcription, a configurable inexpensive text LLM (initial candidate: OpenAI GPT-6 Luna), and Cartesia speech synthesis.
- In-memory conversation history and a new-conversation control.
- Visible transcripts, model responses, stage timings, and available usage data.
- Separate modules for testing each pipeline stage independently.

## Implementation plan

1. Implement and verify the three pipeline stages separately.
2. Connect them to a responsive desktop interface with recording and playback controls.
3. Add local configuration, bounded conversation history, response limits, and error handling.
4. Verify the application on Windows and package it as a desktop executable.

## Development status

Planning and repository setup. Application code has not been implemented yet.

## Local data and credentials

Keep API keys in local configuration, never in source files. `.env` files are ignored, except for a future `.env.example` containing placeholders only.

Recordings, transcripts, and logs belong in the ignored `recordings/`, `transcripts/`, and `logs/` directories. Review staged changes before committing; ignore rules do not protect secrets placed in tracked files.
