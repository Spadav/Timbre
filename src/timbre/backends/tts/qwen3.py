from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Any

from timbre.backends.base import TTSBackend
from timbre.errors import BackendUnavailable
from timbre.wav import pcm_wav_bytes

DEFAULT_QWEN3_VOICES = [
    "Vivian",
    "Serena",
    "Uncle_Fu",
    "Dylan",
    "Eric",
    "Ryan",
    "Aiden",
    "Ono_Anna",
    "Sohee",
]

QWEN3_MODEL_REPOS = {
    "0.6b-base": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
    "0.6b-customvoice": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
    "1.7b-base": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
    "1.7b-customvoice": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
}


class Qwen3Backend(TTSBackend):
    name = "qwen3"

    def __init__(self, config: dict[str, Any], voices_dir: str | None = None) -> None:
        super().__init__(config, voices_dir)
        self._model: Any = None
        self._generation_lock = threading.Lock()
        self._voice_prompt_cache: dict[str, Any] = {}

    async def _load(self) -> None:
        def load() -> Any:
            try:
                import torch
                from qwen_tts import Qwen3TTSModel
            except ImportError as exc:
                raise BackendUnavailable(
                    "Install Qwen3 support with: pip install 'timbre-voice[qwen3]'"
                ) from exc

            source = _model_source(self.config)
            device = _resolve_device(str(self.config.get("device", "cuda:auto")), torch)
            dtype = _resolve_dtype(str(self.config.get("dtype", "auto")), device, torch)
            try:
                torch.set_float32_matmul_precision("high")
            except Exception:
                pass

            kwargs = {"device_map": device, "dtype": dtype}
            last_error: Exception | None = None
            for attention in _attention_attempts(self.config):
                try:
                    return Qwen3TTSModel.from_pretrained(
                        source,
                        **kwargs,
                        attn_implementation=attention,
                    )
                except Exception as exc:
                    last_error = exc

            raise BackendUnavailable(f"Qwen3 model failed to load: {last_error}")

        self._model = await asyncio.to_thread(load)

    async def synthesize(self, text: str, voice: str, **opts: Any) -> bytes:
        await self.ensure_loaded()

        def run() -> bytes:
            model = self._model
            if model is None:
                raise BackendUnavailable("Qwen3 backend is not loaded.")

            language = str(opts.get("lang") or self.config.get("language", "Auto"))
            speed = float(opts.get("speed") or self.config.get("speed", 1.0))
            instruct = opts.get("instruct") or self.config.get("instruct")

            with self._generation_lock:
                if _is_cloned_voice(voice, self.voices_dir):
                    audio, sample_rate = self._generate_cloned(model, text, voice, language, speed)
                else:
                    audio, sample_rate = _generate_native(
                        model, text, voice, language, instruct, speed
                    )
            return pcm_wav_bytes(audio, sample_rate)

        return await asyncio.to_thread(run)

    async def prepare_voice_clone(self, voice: str) -> dict[str, str]:
        await self.ensure_loaded()

        def run() -> dict[str, str]:
            reference = _reference_path(voice, self.voices_dir)
            if reference is None:
                return {
                    "backend": self.name,
                    "voice": voice,
                    "source": "",
                    "cache": "",
                    "status": "missing",
                }
            model = self._model
            if model is None:
                raise BackendUnavailable("Qwen3 backend is not loaded.")
            prompt = self._voice_prompt(model, voice, reference)
            return {
                "backend": self.name,
                "voice": voice,
                "source": str(reference),
                "cache": f"memory:{id(prompt)}",
                "status": "ready",
            }

        return await asyncio.to_thread(run)

    async def _unload(self) -> None:
        self._model = None
        self._voice_prompt_cache.clear()

    @property
    def voices(self) -> list[str]:
        cloned = _cloned_voices(self.voices_dir)
        if _model_type(self.config) == "base":
            return cloned
        return sorted(set(DEFAULT_QWEN3_VOICES + cloned))

    def _generate_cloned(
        self,
        model: Any,
        text: str,
        voice: str,
        language: str,
        speed: float,
    ) -> tuple[Any, int]:
        if _model_type(self.config) != "base":
            raise BackendUnavailable(
                "Qwen3 voice cloning requires an active Base model profile. "
                "Set qwen3:0.6b-base or qwen3:1.7b-base active first."
            )
        reference = _reference_path(voice, self.voices_dir)
        if reference is None:
            raise BackendUnavailable(f"Qwen3 cloned voice '{voice}' has no reference audio.")
        prompt = self._voice_prompt(model, voice, reference)
        wavs, sample_rate = model.generate_voice_clone(
            text=text,
            language=language,
            voice_clone_prompt=prompt,
        )
        return _apply_speed(wavs[0], speed), int(sample_rate)

    def _voice_prompt(self, model: Any, voice: str, reference: Path) -> Any:
        ref_text = _reference_text(reference)
        x_vector_only = bool(self.config.get("x_vector_only_mode", not ref_text))
        cache_key = f"{voice}:{reference.stat().st_mtime_ns}:{x_vector_only}:{ref_text or ''}"
        cached = self._voice_prompt_cache.get(cache_key)
        if cached is not None:
            return cached
        prompt = model.create_voice_clone_prompt(
            ref_audio=str(reference),
            ref_text=ref_text,
            x_vector_only_mode=x_vector_only,
        )
        self._voice_prompt_cache = {cache_key: prompt}
        return prompt


def _model_source(config: dict[str, Any]) -> str:
    model_key = str(config.get("model", "1.7b-customvoice")).lower()
    repo_id = str(config.get("repo_id") or QWEN3_MODEL_REPOS.get(model_key, model_key))
    model_path = config.get("model_path")
    if not model_path:
        return repo_id

    path = Path(str(model_path)).expanduser()
    if path.exists() and any(path.iterdir()):
        return str(path)
    if not repo_id:
        raise BackendUnavailable(
            f"Qwen3 model path '{path}' is empty and no repo_id is configured."
        )

    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise BackendUnavailable("Install huggingface-hub to download Qwen3 models.") from exc
    path.mkdir(parents=True, exist_ok=True)
    return str(snapshot_download(repo_id=repo_id, local_dir=path))


def _resolve_device(device: str, torch: Any) -> str:
    device = device.strip().lower()
    if device in {"", "auto", "cuda", "cuda:auto", "cuda:best"}:
        if not torch.cuda.is_available():
            if device.startswith("cuda"):
                raise BackendUnavailable("Qwen3 is configured for CUDA, but CUDA is not available.")
            return "cpu"
        return _best_cuda_device(torch)
    if device.startswith("cuda") and not torch.cuda.is_available():
        raise BackendUnavailable("Qwen3 is configured for CUDA, but CUDA is not available.")
    return device


def _best_cuda_device(torch: Any) -> str:
    device_count = int(torch.cuda.device_count())
    if device_count <= 0:
        raise BackendUnavailable("Qwen3 is configured for CUDA, but no CUDA devices are visible.")

    best_index = 0
    best_free = -1
    for index in range(device_count):
        try:
            with torch.cuda.device(index):
                free, _total = torch.cuda.mem_get_info()
        except Exception:
            props = torch.cuda.get_device_properties(index)
            free = int(getattr(props, "total_memory", 0))
        if int(free) > best_free:
            best_index = index
            best_free = int(free)
    return f"cuda:{best_index}"


def _resolve_dtype(dtype: str, device: str, torch: Any) -> Any:
    if dtype in {"", "auto"}:
        return torch.bfloat16 if device.startswith("cuda") else torch.float32
    if dtype in {"bfloat16", "bf16"}:
        return torch.bfloat16
    if dtype in {"float16", "fp16"}:
        return torch.float16
    return torch.float32


def _attention_attempts(config: dict[str, Any]) -> list[str]:
    configured = config.get("attention")
    if isinstance(configured, list):
        attempts = [str(item) for item in configured if str(item)]
    elif configured:
        attempts = [str(configured)]
    else:
        attempts = ["flash_attention_2", "sdpa", "eager"]
    if "eager" not in attempts:
        attempts.append("eager")
    return attempts


def _generate_native(
    model: Any,
    text: str,
    voice: str,
    language: str,
    instruct: Any,
    speed: float,
) -> tuple[Any, int]:
    try:
        wavs, sample_rate = model.generate_custom_voice(
            text=text,
            speaker="Vivian" if voice == "default" else voice,
            language=language,
            instruct=instruct,
        )
    except Exception as exc:
        raise BackendUnavailable(f"Qwen3 voice '{voice}' is not available for this model.") from exc
    return _apply_speed(wavs[0], speed), int(sample_rate)


def _apply_speed(audio: Any, speed: float) -> Any:
    if speed == 1.0:
        return audio
    try:
        import numpy as np
        import librosa

        return librosa.effects.time_stretch(np.asarray(audio).astype("float32"), rate=speed)
    except ImportError as exc:
        raise BackendUnavailable(
            "Qwen3 speed control requires librosa. Install Qwen3 support with: "
            "pip install 'timbre-voice[qwen3]'"
        ) from exc


def _model_type(config: dict[str, Any]) -> str:
    configured = str(config.get("model_type", "")).lower()
    if configured:
        return configured
    model = str(config.get("model", "")).lower()
    return "base" if "base" in model and "customvoice" not in model else "customvoice"


def _cloned_voices(voices_dir: str | None) -> list[str]:
    if not voices_dir:
        return []
    root = Path(voices_dir)
    if not root.exists():
        return []
    return sorted(path.name for path in root.iterdir() if path.is_dir())


def _is_cloned_voice(voice: str, voices_dir: str | None) -> bool:
    return _reference_path(voice, voices_dir) is not None


def _reference_path(voice: str, voices_dir: str | None) -> Path | None:
    if not voices_dir:
        return None
    voice_dir = Path(voices_dir) / voice
    if not voice_dir.exists():
        return None
    return next((path for path in voice_dir.iterdir() if path.name.startswith("reference.")), None)


def _reference_text(reference: Path) -> str | None:
    text_path = reference.with_suffix(".txt")
    if not text_path.exists():
        text_path = reference.parent / "reference.txt"
    if not text_path.exists():
        return None
    text = text_path.read_text(encoding="utf-8").strip()
    return text or None
