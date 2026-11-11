"""Qt audio capture/playback; recordings and synthesized audio stay in memory."""

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QObject, Signal
from PySide6.QtMultimedia import QAudio, QAudioFormat, QAudioSink, QAudioSource, QMediaDevices

from .providers import make_wav, wav_info


class AudioIO(QObject):
    playback_finished = Signal()
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.source = None
        self.sink = None
        self.capture_buffer = None
        self.play_buffer = None
        self.format = None
        self.max_bytes = 0
        self.recording_error = ""

    def start_recording(self, device, max_seconds: int):
        self.stop_playback()
        if device.isNull():
            raise RuntimeError("No microphone found. Connect one and check Windows microphone permissions.")
        fmt = QAudioFormat()
        fmt.setSampleRate(device.preferredFormat().sampleRate())
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if not device.isFormatSupported(fmt):
            fmt.setChannelCount(2)
        if not device.isFormatSupported(fmt):
            raise RuntimeError("This microphone does not support 16-bit PCM. Choose another input device.")
        self.format = fmt
        self.max_bytes = max_seconds * fmt.sampleRate() * fmt.channelCount() * 2
        self.recording_error = ""
        self.capture_buffer = bytearray()
        self.source = QAudioSource(device, fmt, self)
        self.source.stateChanged.connect(self._record_state)
        self.capture_device = self.source.start()
        if self.capture_device is None or self.source.error() != QAudio.Error.NoError:
            self.discard_recording()
            raise RuntimeError("Cannot open microphone. Check Windows Settings > Privacy & security > Microphone.")
        self.capture_device.readyRead.connect(self._read)

    def _record_state(self, state):
        if self.source and self.source.error() != QAudio.Error.NoError:
            self.recording_error = "Microphone stopped unexpectedly. Check the input device and record again."

    def _read(self):
        if self.source and self.capture_device:
            data = bytes(self.capture_device.readAll())
            available = max(0, self.max_bytes - len(self.capture_buffer))
            self.capture_buffer.extend(data[:available])

    def stop_recording(self) -> bytes:
        if not self.source:
            raise RuntimeError("No recording is active.")
        self._read()
        error = self.recording_error
        pcm = bytes(self.capture_buffer)
        fmt = self.format
        self.discard_recording()
        if error:
            raise RuntimeError(error)
        alignment = fmt.channelCount() * 2
        pcm = pcm[:len(pcm) // alignment * alignment]
        if len(pcm) < fmt.sampleRate() * alignment // 5:
            raise RuntimeError("Recording was too short. Please speak for at least a moment.")
        return make_wav(pcm, fmt.sampleRate(), fmt.channelCount())

    def discard_recording(self):
        if self.source:
            self.source.stop()
            self.source.deleteLater()
            self.source = None
        self.capture_buffer = None
        self.capture_device = None

    def play(self, audio: bytes):
        self.stop_playback()
        rate, channels, pcm = wav_info(audio)
        device = QMediaDevices.defaultAudioOutput()
        if device.isNull():
            raise RuntimeError("No audio output device is available.")
        fmt = QAudioFormat()
        fmt.setSampleRate(rate)
        fmt.setChannelCount(channels)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if not device.isFormatSupported(fmt):
            raise RuntimeError("Audio output does not support this WAV format. Choose another Windows output device.")
        self.play_buffer = QBuffer(self)
        self.play_buffer.setData(QByteArray(pcm))
        self.play_buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self.sink = QAudioSink(device, fmt, self)
        self.sink.stateChanged.connect(self._play_state)
        self.sink.start(self.play_buffer)

    def _play_state(self, state):
        if not self.sink:
            return
        if self.sink.error() != QAudio.Error.NoError:
            self.stop_playback()
            self.error.emit("Playback failed. Check your Windows output device.")
        elif state == QAudio.State.IdleState:
            self.stop_playback()
            self.playback_finished.emit()

    def stop_playback(self):
        if self.sink:
            sink, self.sink = self.sink, None
            sink.stop()
            sink.deleteLater()
        if self.play_buffer:
            self.play_buffer.close()
            self.play_buffer.deleteLater()
            self.play_buffer = None
