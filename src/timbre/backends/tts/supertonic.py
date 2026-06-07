from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from timbre.backends.base import TTSBackend
from timbre.errors import BackendUnavailable
from timbre.wav import pcm_wav_bytes


class SupertonicBackend(TTSBackend):
    name = "supertonic"

    def __init__(self, config: dict[str, Any], voices_dir: str | None = None) -> None:
        super().__init__(config, voices_dir)
        self._engine: Any = None

    async def _load(self) -> None:
        def load() -> Any:
            try:
                import supertonic
            except ImportError as exc:
                raise BackendUnavailable(
                    "Install Supertonic with: pip install 'timbre-voice[supertonic]'"
                ) from exc
            for attr in ("TTS", "Supertonic", "SupertonicTTS"):
                if hasattr(supertonic, attr):
                    cls = getattr(supertonic, attr)
                    kwargs = {}
                    if self.config.get("model_path"):
                        kwargs["model_dir"] = self.config["model_path"]
                    return cls(**_filter_constructor_kwargs(cls, kwargs))
            raise BackendUnavailable("Supertonic is installed, but no supported engine class was found.")

        self._engine = await asyncio.to_thread(load)

    async def synthesize(self, text: str, voice: str, **opts: Any) -> bytes:
        await self.ensure_loaded()

        def run() -> bytes:
            style = _style_for_voice(self._engine, voice, self.voices_dir)
            kwargs = {
                "voice_style": style,
                "total_steps": int(opts.get("steps", self.config.get("steps", 8))),
                "speed": float(opts.get("speed", self.config.get("speed", 1.05))),
                "lang": opts.get("lang", self.config.get("lang", "en")),
            }
            wav, _meta = self._engine.synthesize(text, **kwargs)
            return _array_to_wav(wav, int(self.config.get("sample_rate", 44100)))

        return await asyncio.to_thread(run)

    async def _unload(self) -> None:
        self._engine = None

    @property
    def voices(self) -> list[str]:
        return ["M1", "F1", "default"]


def _filter_constructor_kwargs(cls: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    import inspect

    try:
        signature = inspect.signature(cls)
    except ValueError:
        return kwargs
    if any(param.kind == param.VAR_KEYWORD for param in signature.parameters.values()):
        return kwargs
    return {key: value for key, value in kwargs.items() if key in signature.parameters}


def _style_for_voice(engine: Any, voice: str, voices_dir: str | None) -> Any:
    cloned = _cloned_style_path(voice, voices_dir)
    if cloned:
        return engine.get_voice_style_from_path(cloned)
    preset = "M1" if voice == "default" else voice
    try:
        return engine.get_voice_style(preset)
    except Exception as exc:
        raise BackendUnavailable(f"Supertonic voice '{voice}' is not available.") from exc


def _cloned_style_path(voice: str, voices_dir: str | None) -> Path | None:
    if not voices_dir:
        return None
    voice_dir = Path(voices_dir) / voice
    if not voice_dir.exists():
        return None
    return next((path for path in voice_dir.iterdir() if path.suffix.lower() == ".json"), None)


def _array_to_wav(audio: Any, sample_rate: int) -> bytes:
    return pcm_wav_bytes(audio, sample_rate)
