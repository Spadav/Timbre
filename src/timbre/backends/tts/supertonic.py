from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from timbre.backends.base import TTSBackend
from timbre.errors import BackendUnavailable
from timbre.wav import pcm_wav_bytes

OPENAI_TO_SUPERTONIC = {
    "alloy": "F1",
    "echo": "M1",
    "fable": "M2",
    "nova": "F2",
    "onyx": "M3",
    "shimmer": "F3",
}
NATIVE_VOICES = ["M1", "M2", "M3", "M4", "M5", "F1", "F2", "F3", "F4", "F5"]
DEFAULT_VOICE = "M1"


class SupertonicBackend(TTSBackend):
    name = "supertonic"

    def __init__(self, config: dict[str, Any], voices_dir: str | None = None) -> None:
        super().__init__(config, voices_dir)
        self._engine: Any = None
        self._voice_cache: dict[str, Any] = {}

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
                    kwargs = {
                        "model": self.config.get("model", "supertonic-3"),
                        "auto_download": bool(self.config.get("auto_download", True)),
                    }
                    if self.config.get("model_path"):
                        kwargs["model_dir"] = self.config["model_path"]
                    if self.config.get("intra_op_num_threads") is not None:
                        kwargs["intra_op_num_threads"] = int(self.config["intra_op_num_threads"])
                    if self.config.get("inter_op_num_threads") is not None:
                        kwargs["inter_op_num_threads"] = int(self.config["inter_op_num_threads"])
                    return cls(**_filter_constructor_kwargs(cls, kwargs))
            raise BackendUnavailable("Supertonic is installed, but no supported engine class was found.")

        self._engine = await asyncio.to_thread(load)
        self._cache_builtin_voices()

    async def synthesize(self, text: str, voice: str, **opts: Any) -> bytes:
        await self.ensure_loaded()

        def run() -> bytes:
            style = self._style_for_voice(voice)
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
        self._voice_cache.clear()

    @property
    def voices(self) -> list[str]:
        return ["default", *OPENAI_TO_SUPERTONIC, *NATIVE_VOICES]

    def _cache_builtin_voices(self) -> None:
        for voice in self.voices:
            try:
                self._voice_cache[voice] = _style_for_voice(self._engine, voice, self.voices_dir)
            except BackendUnavailable:
                continue

    def _style_for_voice(self, voice: str) -> Any:
        if voice not in self._voice_cache:
            self._voice_cache[voice] = _style_for_voice(self._engine, voice, self.voices_dir)
        return self._voice_cache[voice]


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
    preset = DEFAULT_VOICE if voice == "default" else OPENAI_TO_SUPERTONIC.get(voice, voice)
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
