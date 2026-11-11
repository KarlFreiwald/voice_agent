"""Desktop UI. All provider work runs on one background thread at a time."""

import json
from time import monotonic

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtMultimedia import QMediaDevices
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QSplitter,
    QVBoxLayout, QWidget)
from PySide6.QtCore import Qt

from .audio import AudioIO
from .pipeline import Turn, build_pipeline


class TurnWorker(QThread):
    progress = Signal(str, dict)
    completed = Signal(object)

    def __init__(self, pipeline, *, text=None, audio=None, parent=None):
        super().__init__(parent)
        self.pipeline, self.text, self.audio = pipeline, text, audio

    def run(self):
        try:
            turn = self.pipeline.run(text=self.text, audio=self.audio, event=self.progress.emit)
        except Exception:
            # Never leak arbitrary exception strings that might contain credentials.
            turn = Turn(error="Unexpected pipeline error. Check configuration and run the offline tests.")
        self.completed.emit(turn)


class MainWindow(QMainWindow):
    def __init__(self, settings, demo=False):
        super().__init__()
        self.settings = settings
        self.pipeline = build_pipeline(settings, demo)
        self.demo = demo
        self.worker = None
        self.recording = False
        self.last_input = b""
        self.last_output = b""
        self.record_started = 0
        self.audio = AudioIO(self)
        self.audio.playback_finished.connect(lambda: self.status.setText("Ready"))
        self.audio.error.connect(self.show_error)
        self.setWindowTitle("Voice Agent" + (" — Demo" if demo else ""))
        self.resize(1000, 760)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        title = QLabel("Voice Agent")
        title.setStyleSheet("font-size: 26px; font-weight: 600;")
        layout.addWidget(title)
        note = ("DEMO — simulated transcript and answer; playback is a short tone. No API calls."
                if demo else "English voice chat · Record, then stop and send · Audio and conversations stay in app memory locally.")
        banner = QLabel(note)
        banner.setWordWrap(True)
        layout.addWidget(banner)
        if not demo:
            missing = [name.upper() for name in ("deepgram_api_key", "openai_api_key", "cartesia_api_key")
                       if not getattr(settings, name).strip()]
            if missing:
                warning = QLabel("Setup needed: " + ", ".join(missing) + ". Edit config.local.json and restart.")
                warning.setWordWrap(True)
                layout.addWidget(warning)

        devices_row = QHBoxLayout()
        devices_row.addWidget(QLabel("Microphone"))
        self.devices = QComboBox()
        self.devices.setMinimumWidth(260)
        devices_row.addWidget(self.devices, 1)
        self.refresh = QPushButton("Refresh devices")
        self.refresh.clicked.connect(self.refresh_devices)
        devices_row.addWidget(self.refresh)
        self.autoplay = QCheckBox("Speak replies")
        self.autoplay.setChecked(True)
        devices_row.addWidget(self.autoplay)
        layout.addLayout(devices_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.chat = QPlainTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setPlaceholderText("Your conversation will appear here.")
        self.chat.document().setMaximumBlockCount(1500)
        splitter.addWidget(self.chat)
        inspector_panel = QWidget()
        inspection_layout = QVBoxLayout(inspector_panel)
        inspection_layout.setContentsMargins(0, 0, 0, 0)
        inspection_layout.addWidget(QLabel("Inspect the latest turn"))
        self.inspector = QPlainTextEdit()
        self.inspector.setReadOnly(True)
        self.inspector.setPlaceholderText("Models, transcript, response, timings and usage will appear here.\nNo credentials are displayed.")
        inspection_layout.addWidget(self.inspector)
        splitter.addWidget(inspector_panel)
        splitter.setSizes([600, 400])
        layout.addWidget(splitter, 1)

        text_row = QHBoxLayout()
        self.text = QLineEdit()
        self.text.setMaxLength(12000)
        self.text.setPlaceholderText("Or type a message to test the LLM → speech stages")
        self.text.returnPressed.connect(self.send_text)
        text_row.addWidget(self.text, 1)
        self.send = QPushButton("Send text")
        self.send.clicked.connect(self.send_text)
        text_row.addWidget(self.send)
        layout.addLayout(text_row)

        controls = QHBoxLayout()
        self.record = QPushButton("Record")
        self.record.setMinimumHeight(56)
        self.record.clicked.connect(self.toggle_record)
        controls.addWidget(self.record, 2)
        self.stop = QPushButton("Stop playback")
        self.stop.clicked.connect(self.stop_playback)
        controls.addWidget(self.stop)
        self.reset = QPushButton("New conversation")
        self.reset.clicked.connect(self.new_conversation)
        controls.addWidget(self.reset)
        layout.addLayout(controls)

        replay = QHBoxLayout()
        self.replay_input = QPushButton("Replay recording")
        self.replay_input.clicked.connect(lambda: self.play(self.last_input))
        self.replay_output = QPushButton("Replay reply")
        self.replay_output.clicked.connect(lambda: self.play(self.last_output))
        replay.addWidget(self.replay_input)
        replay.addWidget(self.replay_output)
        layout.addLayout(replay)
        self.status = QLabel("Ready")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addWidget(QLabel("Usage is measured, not a billing quote. No automatic API retries. No recordings saved to disk."))
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.tick)
        self.refresh_devices()
        self.update_controls()

    def refresh_devices(self):
        self.devices.clear()
        self.input_devices = QMediaDevices.audioInputs()
        default = QMediaDevices.defaultAudioInput()
        for index, device in enumerate(self.input_devices):
            self.devices.addItem(device.description())
            if device.id() == default.id():
                self.devices.setCurrentIndex(index)

    def update_controls(self):
        busy = self.worker is not None
        for control in (self.send, self.text, self.reset, self.refresh, self.devices):
            control.setEnabled(not busy and not self.recording)
        self.record.setEnabled(not busy)
        self.replay_input.setEnabled(bool(self.last_input) and not busy and not self.recording)
        self.replay_output.setEnabled(bool(self.last_output) and not busy and not self.recording)
        self.record.setText("Stop and send" if self.recording else "Record")

    def toggle_record(self):
        if self.worker is not None:
            return
        if self.recording:
            self.recording = False
            self.timer.stop()
            try:
                self.last_input = self.audio.stop_recording()
                self.start_turn(audio=self.last_input)
            except Exception as exc:
                self.show_error(str(exc))
            self.update_controls()
            return
        if not self.input_devices:
            self.show_error("No microphone found. Connect one and refresh devices.")
            return
        try:
            self.audio.start_recording(self.input_devices[self.devices.currentIndex()], self.settings.max_recording_seconds)
        except Exception as exc:
            self.show_error(str(exc))
            return
        self.recording = True
        self.record_started = monotonic()
        self.timer.start()
        self.tick()
        self.update_controls()

    def tick(self):
        elapsed = monotonic() - self.record_started
        self.status.setText(f"Recording · {elapsed:.1f}s / {self.settings.max_recording_seconds}s")
        if self.audio.recording_error:
            self.timer.stop()
            self.recording = False
            error = self.audio.recording_error
            self.audio.discard_recording()
            self.show_error(error)
            self.update_controls()
        elif elapsed >= self.settings.max_recording_seconds:
            self.toggle_record()

    def send_text(self):
        if self.worker is not None or self.recording:
            return
        value = self.text.text().strip()
        if value:
            self.last_input = b""
            self.text.clear()
            self.start_turn(text=value)

    def start_turn(self, **kwargs):
        self.stop_playback()
        self.last_output = b""
        self.inspector.clear()
        self.worker = TurnWorker(self.pipeline, parent=self, **kwargs)
        self.worker.progress.connect(self.progress)
        self.worker.completed.connect(self.complete)
        self.worker.finished.connect(self.worker_finished)
        self.update_controls()
        self.worker.start()

    def progress(self, kind, data):
        if kind == "stage":
            self.status.setText({"transcription": "Transcribing…", "language_model": "Thinking…",
                                 "synthesis": "Generating speech…"}[data["name"]])
        else:
            who = "You" if kind == "transcript" else "Assistant"
            self.chat.appendPlainText(f"{who}: {data['text']}\n")
            self.chat.moveCursor(QTextCursor.MoveOperation.End)
            self.inspector.appendPlainText(f"{kind}:\n{data['text']}\n")

    def complete(self, turn):
        self.last_output = turn.audio
        report = {"mode": "demo" if self.demo else "live",
                  "models": {"stt": self.settings.stt_model, "llm": self.settings.llm_model,
                             "tts": self.settings.tts_model},
                  "language": self.settings.language, "voice_id": self.settings.voice_id,
                  "transcript": turn.transcript, "response": turn.response,
                  "seconds": {key: round(value, 3) for key, value in turn.timings.items()},
                  "usage": turn.usage, "error": turn.error}
        self.inspector.setPlainText(json.dumps(report, indent=2, ensure_ascii=False))
        if turn.error:
            self.show_error(turn.error)
        elif turn.audio and self.autoplay.isChecked():
            self.play(turn.audio)
        else:
            self.status.setText("Ready")

    def worker_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.update_controls()

    def play(self, audio):
        if not audio:
            return
        self.status.setText("Playing demo tone…" if self.demo else "Speaking…")
        try:
            self.audio.play(audio)
        except Exception as exc:
            self.show_error(str(exc))

    def stop_playback(self):
        self.audio.stop_playback()
        if self.worker is None and not self.recording:
            self.status.setText("Ready")

    def show_error(self, message):
        self.status.setText("Error: " + message)

    def new_conversation(self):
        self.stop_playback()
        self.pipeline.reset()
        self.last_input = self.last_output = b""
        self.chat.clear()
        self.inspector.clear()
        self.update_controls()

    def closeEvent(self, event):
        if self.worker is not None:
            QMessageBox.information(self, "Request in progress", "Please wait for the current turn to finish before closing. Each API request has a timeout.")
            event.ignore()
            return
        self.audio.discard_recording()
        self.audio.stop_playback()
        event.accept()


def launch(settings, demo=False):
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    window = MainWindow(settings, demo)
    window.show()
    return app.exec()
