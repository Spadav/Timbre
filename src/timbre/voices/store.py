from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


@dataclass(slots=True)
class VoiceRecord:
    name: str
    path: Path
    audio_path: Path | None


class VoiceStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[VoiceRecord]:
        records: list[VoiceRecord] = []
        for path in sorted(self.root.iterdir()):
            if not path.is_dir():
                continue
            audio = next((item for item in path.iterdir() if item.name.startswith("reference.")), None)
            records.append(VoiceRecord(path.name, path, audio))
        return records

    async def save_upload(self, name: str, upload: UploadFile) -> VoiceRecord:
        if not SAFE_NAME.match(name):
            raise ValueError("Voice name must be 1-80 chars: letters, numbers, dot, dash, underscore.")
        ext = Path(upload.filename or "reference.wav").suffix.lower() or ".wav"
        voice_dir = self.root / name
        voice_dir.mkdir(parents=True, exist_ok=True)
        audio_path = voice_dir / f"reference{ext}"
        with audio_path.open("wb") as handle:
            while chunk := await upload.read(1024 * 1024):
                handle.write(chunk)
        return VoiceRecord(name, voice_dir, audio_path)

    def delete(self, name: str) -> bool:
        path = self.root / name
        if not path.exists():
            return False
        shutil.rmtree(path)
        return True
