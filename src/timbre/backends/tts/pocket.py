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
            language = self.config.get("language") or self.config.get("model") or "english"
            load_kwargs: dict[str, Any] = {
                "language": language,
                "temp": float(self.config.get("temp", 0.7)),
                "lsd_decode_steps": int(self.config.get("lsd_decode_steps", 1)),
                "eos_threshold": float(self.config.get("eos_threshold", -4.0)),
                "quantize": bool(self.config.get("quantize", False)),
            }
            if self.config.get("noise_clamp") is not None:
                load_kwargs["noise_clamp"] = float(self.config["noise_clamp"])
            if self.config.get("config"):
                load_kwargs.pop("language", None)
                load_kwargs["config"] = self.config["config"]
            model = TTSModel.load_model(**load_kwargs)
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
            result = engine.generate_audio(state, text, **_generation_kwargs(self.config, opts))
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
        preset = ["default", *_pocket_preset_voices()]
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


def _generation_kwargs(config: dict[str, Any], opts: dict[str, Any]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"max_tokens": int(opts.get("max_tokens", config.get("max_tokens", 50)))}
    frames_after_eos = opts.get("frames_after_eos", config.get("frames_after_eos"))
    if frames_after_eos is not None:
        kwargs["frames_after_eos"] = int(frames_after_eos)
    return kwargs


def _pocket_preset_voices() -> list[str]:
    try:
        from pocket_tts.models.tts_model import _ORIGINS_OF_PREDEFINED_VOICES

        return sorted(_ORIGINS_OF_PREDEFINED_VOICES)
    except Exception:
        return [
            "alba",
            "anna",
            "azelma",
            "bill_boerst",
            "caro_davy",
            "charles",
            "cosette",
            "eponine",
            "estelle",
            "eve",
            "fantine",
            "george",
            "giovanni",
            "jane",
            "javert",
            "jean",
            "juergen",
            "lola",
            "marius",
            "mary",
            "michael",
            "paul",
            "peter_yearsley",
            "rafael",
            "stuart_bell",
            "vera",
        ]
