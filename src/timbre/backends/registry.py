from __future__ import annotations

from timbre.backends.stt.parakeet import ParakeetBackend
from timbre.backends.stt.whisper import WhisperBackend
from timbre.backends.tts.pocket import PocketBackend
from timbre.backends.tts.qwen3 import Qwen3Backend
from timbre.backends.tts.supertonic import SupertonicBackend

TTS_BACKENDS = {
    "pocket": PocketBackend,
    "qwen3": Qwen3Backend,
    "supertonic": SupertonicBackend,
}

STT_BACKENDS = {
    "whisper": WhisperBackend,
    "parakeet": ParakeetBackend,
}
