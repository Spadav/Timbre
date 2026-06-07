from __future__ import annotations

from timbre.backends.stt.parakeet import ParakeetBackend
from timbre.backends.stt.whisper import WhisperBackend
from timbre.backends.tts.pocket import PocketBackend
from timbre.backends.tts.supertonic import SupertonicBackend

TTS_BACKENDS = {
    "pocket": PocketBackend,
    "supertonic": SupertonicBackend,
}

STT_BACKENDS = {
    "whisper": WhisperBackend,
    "parakeet": ParakeetBackend,
}
