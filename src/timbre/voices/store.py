from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac"}


@dataclass(slots=True)
class VoiceRecord:
    name: str
    path: Path
    audio_path: Path | None
    caches: list[Path]


class VoiceStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[VoiceRecord]:
        records: list[VoiceRecord] = []
        for path in sorted(self.root.iterdir()):
            if not path.is_dir():
                continue
            audio = _reference_audio(path)
            caches = sorted(path.glob("*.safetensors"))
            records.append(VoiceRecord(path.name, path, audio, caches))
        return records

    def get(self, name: str) -> VoiceRecord | None:
        if not SAFE_NAME.match(name):
            return None
        path = self.root / name
        if not path.is_dir():
            return None
        audio = _reference_audio(path)
        return VoiceRecord(path.name, path, audio, sorted(path.glob("*.safetensors")))

    async def save_upload(self, name: str, upload: UploadFile) -> VoiceRecord:
        if not SAFE_NAME.match(name):
            raise ValueError("Voice name must be 1-80 chars: letters, numbers, dot, dash, underscore.")
        ext = Path(upload.filename or "reference.wav").suffix.lower() or ".wav"
        if ext not in SUPPORTED_AUDIO_EXTENSIONS:
            allowed = ", ".join(sorted(SUPPORTED_AUDIO_EXTENSIONS))
            raise ValueError(f"Voice reference must be one of: {allowed}.")
        voice_dir = self.root / name
        voice_dir.mkdir(parents=True, exist_ok=True)
        audio_path = voice_dir / f"reference{ext}"
        with audio_path.open("wb") as handle:
            while chunk := await upload.read(1024 * 1024):
                handle.write(chunk)
        return VoiceRecord(name, voice_dir, audio_path, sorted(voice_dir.glob("*.safetensors")))

    def delete(self, name: str) -> bool:
        path = self.root / name
        if not path.exists():
            return False
        shutil.rmtree(path)
        return True


def _reference_audio(path: Path) -> Path | None:
    return next(
        (
            item
            for item in path.iterdir()
            if item.name.startswith("reference.") and item.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
        ),
        None,
    )
