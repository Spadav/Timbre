from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from timbre.backends.base import TTSBackend
from timbre.errors import BackendUnavailable
from timbre.wav import pcm_wav_bytes


class PocketBackend(TTSBackend):
    name = "pocket"

    def __init__(self, config: dict[str, Any], voices_dir: str | None = None) -> None:
        super().__init__(config, voices_dir)
        self._engine: Any = None

    async def _load(self) -> None:
        def load() -> Any:
            try:
                from pocket_tts import TTSModel
            except ImportError as exc:
                raise BackendUnavailable("Install PocketTTS with: pip install 'timbre-voice[pocket]'") from exc
            model = TTSModel.load_model(language=self.config.get("language", "english"))
            device = self.config.get("device", "cpu")
            if device.startswith("cuda"):
                model = model.cuda(_device_index(device))
            else:
                model = model.cpu()
            return model.eval()

        self._engine = await asyncio.to_thread(load)

    async def synthesize(self, text: str, voice: str, **opts: Any) -> bytes:
        await self.ensure_loaded()

        def run() -> bytes:
            engine = self._engine
            if engine is None:
                raise BackendUnavailable("PocketTTS backend is not loaded.")
            state = _voice_state(engine, voice, self.voices_dir, self.config.get("language", "english"))
            max_tokens = int(opts.get("max_tokens", self.config.get("max_tokens", 4096)))
            result = engine.generate_audio(state, text, max_tokens=max_tokens)
            return _tensor_to_wav(result, int(self.config.get("sample_rate", 24000)))

        return await asyncio.to_thread(run)

    async def _unload(self) -> None:
        self._engine = None

    @property
    def voices(self) -> list[str]:
        preset = ["default", "alba", "marius", "javert", "jean", "fantine", "cosette", "eponine", "azelma"]
        if self.voices_dir:
            cloned = [path.name for path in Path(self.voices_dir).iterdir() if path.is_dir()] if Path(self.voices_dir).exists() else []
            return sorted(set(preset + cloned))
        return preset


def _first_method(obj: Any, names: list[str]) -> Any:
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    raise BackendUnavailable(f"No supported synthesize method found on {type(obj).__name__}.")


def _filter_kwargs(method: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    import inspect

    signature = inspect.signature(method)
    if any(param.kind == param.VAR_KEYWORD for param in signature.parameters.values()):
        return kwargs
    return {key: value for key, value in kwargs.items() if key in signature.parameters}


def _coerce_audio_bytes(result: Any) -> bytes:
    if isinstance(result, bytes):
        return result
    if isinstance(result, tuple):
        for value in result:
            if isinstance(value, bytes):
                return value
    if hasattr(result, "read"):
        return result.read()
    if hasattr(result, "export"):
        from io import BytesIO

        output = BytesIO()
        result.export(output, format="wav")
        return output.getvalue()
    raise BackendUnavailable("PocketTTS returned an unsupported audio object.")


def _voice_state(engine: Any, voice: str, voices_dir: str | None, language: str) -> dict[str, Any]:
    cloned = _cloned_reference(voice, voices_dir)
    if cloned:
        return engine.get_state_for_audio_prompt(cloned)
    try:
        preset = "alba" if voice == "default" else voice
        return engine.get_state_for_audio_prompt(preset)
    except Exception as exc:
        raise BackendUnavailable(f"PocketTTS voice '{voice}' is not available.") from exc


def _cloned_reference(voice: str, voices_dir: str | None) -> Path | None:
    if not voices_dir:
        return None
    voice_dir = Path(voices_dir) / voice
    if not voice_dir.exists():
        return None
    return next((path for path in voice_dir.iterdir() if path.name.startswith("reference.")), None)


def _tensor_to_wav(audio: Any, sample_rate: int) -> bytes:
    try:
        import torch

        if isinstance(audio, torch.Tensor):
            audio = audio.detach().cpu().numpy()
    except Exception:
        pass
    return pcm_wav_bytes(audio, sample_rate)


def _device_index(device: str) -> int:
    if ":" not in device:
        return 0
    try:
        return int(device.split(":", 1)[1])
    except ValueError:
        return 0
