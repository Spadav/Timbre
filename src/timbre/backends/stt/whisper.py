from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

from timbre.backends.base import STTBackend
from timbre.errors import BackendUnavailable


class WhisperBackend(STTBackend):
    name = "whisper"

    def __init__(self, config: dict[str, Any], voices_dir: str | None = None) -> None:
        super().__init__(config, voices_dir)
        self._model: Any = None

    async def _load(self) -> None:
        def load() -> Any:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise BackendUnavailable(
                    "Install faster-whisper with: pip install 'timbre-voice[whisper]'"
                ) from exc
            device = self.config.get("device", "cpu")
            compute_type = self.config.get("compute_type", "int8" if device == "cpu" else "float16")
            model_path = self.config.get("model_path")
            model_size_or_path = self.config.get("model_size", "base")
            download_root = None
            if model_path:
                path = Path(model_path)
                if path.exists() and any(path.iterdir()):
                    model_size_or_path = str(path)
                else:
                    download_root = str(path.parent)
            return WhisperModel(
                model_size_or_path,
                device=device.split(":")[0],
                device_index=_device_index(device),
                compute_type=compute_type,
                download_root=download_root,
            )

        self._model = await asyncio.to_thread(load)

    async def transcribe(self, audio: bytes, **opts: Any) -> str:
        await self.ensure_loaded()

        def run() -> str:
            suffix = opts.pop("suffix", ".wav")
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
                handle.write(audio)
                temp_path = Path(handle.name)
            try:
                segments, _info = self._model.transcribe(str(temp_path), **opts)
                return "".join(segment.text for segment in segments).strip()
            finally:
                temp_path.unlink(missing_ok=True)

        return await asyncio.to_thread(run)

    async def _unload(self) -> None:
        self._model = None


def _device_index(device: str) -> int:
    if ":" not in device:
        return 0
    try:
        return int(device.split(":", 1)[1])
    except ValueError:
        return 0
