from __future__ import annotations

import asyncio
import logging
import re
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
    "1.7b-voicedesign": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    "1.7b-customvoice": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
}

LOGGER = logging.getLogger("timbre")


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
            _configure_torch_runtime(torch, self.config)

            kwargs = {"device_map": device, "dtype": dtype}
            last_error: Exception | None = None
            for attention in _attention_attempts(self.config):
                try:
                    model = Qwen3TTSModel.from_pretrained(
                        source,
                        **kwargs,
                        attn_implementation=attention,
                    )
                    LOGGER.info(
                        "qwen.load | ok | model loaded | source=%s device=%s dtype=%s attention=%s",
                        source,
                        device,
                        _dtype_name(dtype),
                        attention,
                    )
                    model = _maybe_compile_model(model, self.config, torch)
                    _warmup_model(model, self.config, self.voices_dir)
                    return model
                except Exception as exc:
                    last_error = exc
                    LOGGER.warning(
                        "qwen.load | fallback | attention failed | attention=%s error=%s",
                        attention,
                        exc,
                    )

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
            generation_kwargs = _generation_kwargs(self.config)
            chunk_chars = _chunk_chars(self.config)

            with self._generation_lock:
                if _is_cloned_voice(voice, self.voices_dir):
                    audio, sample_rate = self._generate_cloned(
                        model,
                        text,
                        voice,
                        language,
                        speed,
                        generation_kwargs=generation_kwargs,
                        chunk_chars=chunk_chars,
                    )
                else:
                    audio, sample_rate = _generate_native(
                        model,
                        text,
                        voice,
                        language,
                        instruct,
                        speed,
                        generation_kwargs=generation_kwargs,
                        chunk_chars=chunk_chars,
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

    async def prepare_clone_reference(
        self,
        voice: str,
        reference: Path,
        *,
        ref_text: str | None = None,
        x_vector_only_mode: bool | None = None,
    ) -> dict[str, str]:
        await self.ensure_loaded()

        def run() -> dict[str, str]:
            if _model_type(self.config) != "base":
                raise BackendUnavailable(
                    "Qwen3 clone preparation requires an active Base model profile. "
                    "Set qwen3:0.6b-base or qwen3:1.7b-base active first."
                )
            model = self._model
            if model is None:
                raise BackendUnavailable("Qwen3 backend is not loaded.")
            prompt = self._voice_prompt_for_reference(
                model,
                reference,
                cache_prefix=voice,
                ref_text=ref_text,
                x_vector_only_mode=x_vector_only_mode,
            )
            return {
                "backend": self.name,
                "voice": voice,
                "source": str(reference),
                "cache": f"memory:{id(prompt)}",
                "status": "ready",
            }

        return await asyncio.to_thread(run)

    async def synthesize_clone(
        self,
        text: str,
        reference: Path,
        *,
        language: str = "Auto",
        speed: float = 1.0,
        ref_text: str | None = None,
        x_vector_only_mode: bool | None = None,
    ) -> bytes:
        await self.ensure_loaded()

        def run() -> bytes:
            model = self._model
            if model is None:
                raise BackendUnavailable("Qwen3 backend is not loaded.")
            if _model_type(self.config) != "base":
                raise BackendUnavailable(
                    "Qwen3 clone mode requires an active Base model profile. "
                    "Set qwen3:0.6b-base or qwen3:1.7b-base active first."
                )
            with self._generation_lock:
                prompt = self._voice_prompt_for_reference(
                    model,
                    reference,
                    ref_text=ref_text,
                    x_vector_only_mode=x_vector_only_mode,
                )
                audio, sample_rate = _generate_by_chunks(
                    lambda chunk: model.generate_voice_clone(
                        text=chunk,
                        language=language,
                        voice_clone_prompt=prompt,
                        **_generation_kwargs(self.config),
                    ),
                    text,
                    _chunk_chars(self.config),
                )
            return pcm_wav_bytes(_apply_speed(audio, speed), int(sample_rate))

        return await asyncio.to_thread(run)

    async def synthesize_custom_voice(
        self,
        text: str,
        speaker: str,
        *,
        language: str = "Auto",
        instruct: str | None = None,
        speed: float = 1.0,
    ) -> bytes:
        await self.ensure_loaded()

        def run() -> bytes:
            model = self._model
            if model is None:
                raise BackendUnavailable("Qwen3 backend is not loaded.")
            if _model_type(self.config) != "customvoice":
                raise BackendUnavailable(
                    "Qwen3 CustomVoice mode requires an active CustomVoice model profile. "
                    "Set qwen3:0.6b-customvoice or qwen3:1.7b-customvoice active first."
                )
            with self._generation_lock:
                audio, sample_rate = _generate_native(
                    model,
                    text,
                    speaker,
                    language,
                    instruct,
                    speed,
                    generation_kwargs=_generation_kwargs(self.config),
                    chunk_chars=_chunk_chars(self.config),
                )
            return pcm_wav_bytes(audio, sample_rate)

        return await asyncio.to_thread(run)

    async def synthesize_voice_design(
        self,
        text: str,
        instruct: str,
        *,
        language: str = "Auto",
        speed: float = 1.0,
    ) -> bytes:
        await self.ensure_loaded()

        def run() -> bytes:
            model = self._model
            if model is None:
                raise BackendUnavailable("Qwen3 backend is not loaded.")
            if _model_type(self.config) != "voice_design":
                raise BackendUnavailable(
                    "Qwen3 VoiceDesign mode requires the active VoiceDesign model profile. "
                    "Set qwen3:1.7b-voicedesign active first."
                )
            with self._generation_lock:
                try:
                    audio, sample_rate = _generate_by_chunks(
                        lambda chunk: model.generate_voice_design(
                            text=chunk,
                            language=language,
                            instruct=instruct,
                            **_generation_kwargs(self.config),
                        ),
                        text,
                        _chunk_chars(self.config),
                    )
                except Exception as exc:
                    raise BackendUnavailable(f"Qwen3 VoiceDesign generation failed: {exc}") from exc
            return pcm_wav_bytes(_apply_speed(audio, speed), int(sample_rate))

        return await asyncio.to_thread(run)

    async def _unload(self) -> None:
        self._model = None
        self._voice_prompt_cache.clear()

    @property
    def voices(self) -> list[str]:
        if _model_type(self.config) == "customvoice":
            return sorted(DEFAULT_QWEN3_VOICES)
        if _model_type(self.config) == "base":
            return _cloned_voices(self.voices_dir)
        return []

    def _generate_cloned(
        self,
        model: Any,
        text: str,
        voice: str,
        language: str,
        speed: float,
        generation_kwargs: dict[str, Any] | None = None,
        chunk_chars: int = 0,
    ) -> tuple[Any, int]:
        if _model_type(self.config) != "base":
            raise BackendUnavailable(
                "Qwen3 voice cloning requires an active Base model profile. "
                "Set qwen3:0.6b-base or qwen3:1.7b-base active first."
            )
        reference = _reference_path(voice, self.voices_dir)
        if reference is None:
            raise BackendUnavailable(f"Qwen3 cloned voice '{voice}' has no reference audio.")
        prompt = self._voice_prompt_for_reference(model, reference)
        audio, sample_rate = _generate_by_chunks(
            lambda chunk: model.generate_voice_clone(
                text=chunk,
                language=language,
                voice_clone_prompt=prompt,
                **(generation_kwargs or {}),
            ),
            text,
            chunk_chars,
        )
        return _apply_speed(audio, speed), int(sample_rate)

    def _voice_prompt(self, model: Any, voice: str, reference: Path) -> Any:
        return self._voice_prompt_for_reference(model, reference, cache_prefix=voice)

    def _voice_prompt_for_reference(
        self,
        model: Any,
        reference: Path,
        *,
        cache_prefix: str | None = None,
        ref_text: str | None = None,
        x_vector_only_mode: bool | None = None,
    ) -> Any:
        ref_text = ref_text if ref_text is not None else _reference_text(reference)
        x_vector_only = (
            bool(x_vector_only_mode)
            if x_vector_only_mode is not None
            else bool(self.config.get("x_vector_only_mode", not ref_text))
        )
        cache_name = cache_prefix or reference.parent.name
        cache_key = f"{cache_name}:{reference.stat().st_mtime_ns}:{x_vector_only}:{ref_text or ''}"
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


def _dtype_name(dtype: Any) -> str:
    return str(dtype).replace("torch.", "")


def _configure_torch_runtime(torch: Any, config: dict[str, Any]) -> None:
    precision = config.get("matmul_precision", "high")
    if precision:
        try:
            torch.set_float32_matmul_precision(str(precision))
        except Exception as exc:
            LOGGER.warning("qwen.load | warning | matmul precision failed | error=%s", exc)

    if "cudnn_benchmark" in config:
        try:
            torch.backends.cudnn.benchmark = _bool_config(config.get("cudnn_benchmark"))
        except Exception as exc:
            LOGGER.warning("qwen.load | warning | cudnn benchmark failed | error=%s", exc)


def _maybe_compile_model(model: Any, config: dict[str, Any], torch: Any) -> Any:
    if not _bool_config(config.get("compile", False)):
        return model
    compile_fn = getattr(torch, "compile", None)
    if not callable(compile_fn):
        LOGGER.warning("qwen.load | warning | torch.compile unavailable")
        return model

    mode = str(config.get("compile_mode") or "reduce-overhead")
    targets = _compile_targets(config)
    compiled_any = False
    for target in targets:
        if target in {"self", "wrapper"}:
            try:
                model = compile_fn(model, mode=mode)
                compiled_any = True
                LOGGER.info("qwen.load | ok | compiled qwen wrapper | mode=%s", mode)
            except Exception as exc:
                LOGGER.warning("qwen.load | warning | compile failed | target=%s error=%s", target, exc)
            continue

        module = getattr(model, target, None)
        if module is None:
            LOGGER.warning("qwen.load | warning | compile target missing | target=%s", target)
            continue
        try:
            setattr(model, target, compile_fn(module, mode=mode))
            compiled_any = True
            LOGGER.info("qwen.load | ok | compiled qwen target | target=%s mode=%s", target, mode)
        except Exception as exc:
            LOGGER.warning("qwen.load | warning | compile failed | target=%s error=%s", target, exc)

    if not compiled_any:
        LOGGER.warning("qwen.load | warning | no qwen compile target was compiled")
    return model


def _compile_targets(config: dict[str, Any]) -> list[str]:
    targets = config.get("compile_targets", ["model"])
    if isinstance(targets, list):
        clean = [str(target).strip() for target in targets if str(target).strip()]
        return clean or ["model"]
    return [str(targets).strip() or "model"]


def _warmup_model(model: Any, config: dict[str, Any], voices_dir: str | None) -> None:
    if not _bool_config(config.get("warmup", False)):
        return
    text = str(config.get("warmup_text") or "Warmup.")
    language = str(config.get("language", "Auto"))
    model_type = _model_type(config)
    kwargs = _generation_kwargs(config)
    try:
        if model_type == "base":
            voice = str(config.get("warmup_voice") or "")
            reference = _reference_path(voice, voices_dir) if voice else None
            if reference is None:
                LOGGER.info("qwen.load | skip | warmup needs warmup_voice clone for base model")
                return
            prompt = model.create_voice_clone_prompt(ref_audio=str(reference), x_vector_only_mode=True)
            model.generate_voice_clone(
                text=text,
                language=language,
                voice_clone_prompt=prompt,
                **kwargs,
            )
        elif model_type == "voice_design":
            instruct = str(config.get("warmup_instruct") or "Neutral studio voice.")
            model.generate_voice_design(text=text, language=language, instruct=instruct, **kwargs)
        else:
            voice = str(config.get("warmup_voice") or "Vivian")
            model.generate_custom_voice(text=text, speaker=voice, language=language, **kwargs)
        LOGGER.info("qwen.load | ok | warmup completed | model_type=%s", model_type)
    except Exception as exc:
        LOGGER.warning("qwen.load | warning | warmup failed | error=%s", exc)


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
    generation_kwargs: dict[str, Any] | None = None,
    chunk_chars: int = 0,
) -> tuple[Any, int]:
    try:
        audio, sample_rate = _generate_by_chunks(
            lambda chunk: model.generate_custom_voice(
                text=chunk,
                speaker="Vivian" if voice == "default" else voice,
                language=language,
                instruct=instruct,
                **(generation_kwargs or {}),
            ),
            text,
            chunk_chars,
        )
    except Exception as exc:
        raise BackendUnavailable(f"Qwen3 voice '{voice}' is not available for this model.") from exc
    return _apply_speed(audio, speed), int(sample_rate)


def _generate_by_chunks(generator: Any, text: str, chunk_chars: int) -> tuple[Any, int]:
    chunks = _split_text(text, chunk_chars)
    audios = []
    sample_rate = 0
    for chunk in chunks:
        wavs, sample_rate = generator(chunk)
        audios.append(wavs[0])
    return _concat_audio(audios), int(sample_rate)


def _split_text(text: str, chunk_chars: int) -> list[str]:
    text = text.strip()
    if not text:
        return [text]
    if chunk_chars <= 0 or len(text) <= chunk_chars:
        return [text]

    sentences = [part.strip() for part in re.split(r"(?<=[.!?;:])\s+", text) if part.strip()]
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > chunk_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(sentence[index : index + chunk_chars] for index in range(0, len(sentence), chunk_chars))
            continue
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > chunk_chars:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [text]


def _concat_audio(audios: list[Any]) -> Any:
    if len(audios) == 1:
        return audios[0]
    try:
        import numpy as np

        return np.concatenate([np.asarray(audio).astype("float32") for audio in audios])
    except ImportError as exc:
        raise BackendUnavailable("Qwen3 chunking requires numpy.") from exc


def _chunk_chars(config: dict[str, Any]) -> int:
    try:
        return max(0, int(config.get("chunk_chars") or 0))
    except (TypeError, ValueError):
        return 0


def _generation_kwargs(config: dict[str, Any]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    for key in ("temperature", "top_p", "repetition_penalty", "subtalker_top_p", "subtalker_temperature"):
        value = config.get(key)
        if value not in {None, ""}:
            kwargs[key] = float(value)
    for key in ("max_new_tokens", "top_k", "subtalker_top_k"):
        value = config.get(key)
        if value not in {None, ""}:
            kwargs[key] = int(value)
    for key in ("do_sample", "subtalker_dosample", "non_streaming_mode"):
        value = config.get(key)
        if value not in {None, ""}:
            kwargs[key] = _bool_config(value)
    return kwargs


def _bool_config(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


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
    if "voice_design" in model or "voicedesign" in model:
        return "voice_design"
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
