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

    async def prepare_voice_clone(self, voice: str) -> dict[str, str]:
        await self.ensure_loaded()

        def run() -> dict[str, str]:
            engine = self._engine
            if engine is None:
                raise BackendUnavailable("PocketTTS backend is not loaded.")
            language = self.config.get("language", "english")
            state, source, cache = _voice_state(
                engine, voice, self.voices_dir, language, return_metadata=True
            )
            return {
                "backend": self.name,
                "voice": voice,
                "source": str(source),
                "cache": str(cache) if cache else "",
                "status": "ready" if state else "missing",
            }

        return await asyncio.to_thread(run)

    async def _unload(self) -> None:
        self._engine = None

    @property
    def voices(self) -> list[str]:
        preset = [
            "default",
            "alba",
            "marius",
            "javert",
            "jean",
            "fantine",
            "cosette",
            "eponine",
            "azelma",
        ]
        if self.voices_dir:
            root = Path(self.voices_dir)
            cloned = [path.name for path in root.iterdir() if path.is_dir()] if root.exists() else []
            return sorted(set(preset + cloned))
        return preset


def _voice_state_with_metadata(
    engine: Any, voice: str, voices_dir: str | None, language: str
) -> tuple[dict[str, Any], Path | str, Path | None]:
    cloned = _cloned_paths(voice, voices_dir, language)
    if cloned:
        reference, cache = cloned
        if cache.exists() and (reference is None or cache.stat().st_mtime >= reference.stat().st_mtime):
            try:
                return engine.get_state_for_audio_prompt(cache), cache, cache
            except Exception:
                cache.unlink(missing_ok=True)
        if reference is None:
            raise BackendUnavailable(f"PocketTTS cloned voice '{voice}' has no reference audio.")
        try:
            state = engine.get_state_for_audio_prompt(reference, truncate=True)
        except TypeError:
            state = engine.get_state_for_audio_prompt(reference)
        _save_state(state, cache)
        return state, reference, cache
    try:
        preset = "alba" if voice == "default" else voice
        return engine.get_state_for_audio_prompt(preset), preset, None
    except Exception as exc:
        raise BackendUnavailable(f"PocketTTS voice '{voice}' is not available.") from exc


def _voice_state(
    engine: Any,
    voice: str,
    voices_dir: str | None,
    language: str,
    return_metadata: bool = False,
) -> dict[str, Any] | tuple[dict[str, Any], Path | str, Path | None]:
    result = _voice_state_with_metadata(engine, voice, voices_dir, language)
    if return_metadata:
        return result
    return result[0]


def _cloned_paths(voice: str, voices_dir: str | None, language: str) -> tuple[Path | None, Path] | None:
    if not voices_dir:
        return None
    voice_dir = Path(voices_dir) / voice
    if not voice_dir.exists():
        return None
    reference = next((path for path in voice_dir.iterdir() if path.name.startswith("reference.")), None)
    cache = voice_dir / f"pocket.{_safe_tag(language)}.safetensors"
    return reference, cache


def _safe_tag(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)


def _save_state(state: dict[str, Any], cache: Path) -> None:
    try:
        from pocket_tts.models.tts_model import export_model_state
    except ImportError as exc:
        raise BackendUnavailable("PocketTTS cannot export cloned voice state.") from exc
    cache.parent.mkdir(parents=True, exist_ok=True)
    export_model_state(state, cache)


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
