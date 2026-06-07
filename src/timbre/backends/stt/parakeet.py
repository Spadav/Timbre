from __future__ import annotations

from typing import Any

from timbre.backends.base import STTBackend
from timbre.errors import BackendUnavailable


class ParakeetBackend(STTBackend):
    name = "parakeet"

    async def _load(self) -> None:
        try:
            import onnxruntime  # noqa: F401
        except ImportError as exc:
            raise BackendUnavailable(
                "Install Parakeet ONNX support with: pip install 'timbre-voice[parakeet]'"
            ) from exc
        raise BackendUnavailable(
            "Parakeet ONNX model files can be downloaded with 'timbre download-models', "
            "but the v1 Python runner needs a concrete model layout before transcription is enabled."
        )

    async def transcribe(self, audio: bytes, **opts: Any) -> str:
        raise BackendUnavailable("Parakeet backend is not enabled yet.")
