from __future__ import annotations

import audioop
import asyncio
from io import BytesIO
import re
import subprocess
import wave
from typing import Any

import numpy as np

from timbre.backends.base import STTBackend
from timbre.errors import BackendUnavailable

TARGET_SR = 16_000

MODEL_CONFIGS = {
    "parakeet-tdt-0.6b-v3": {
        "hf_id": "nemo-parakeet-tdt-0.6b-v3",
        "quantization": "int8",
    },
    "istupakov/parakeet-tdt-0.6b-v3-onnx": {
        "hf_id": "istupakov/parakeet-tdt-0.6b-v3-onnx",
        "quantization": None,
    },
    "grikdotnet/parakeet-tdt-0.6b-fp16": {
        "hf_id": "grikdotnet/parakeet-tdt-0.6b-fp16",
        "quantization": "fp16",
    },
}


class ParakeetBackend(STTBackend):
    name = "parakeet"

    def __init__(self, config: dict[str, Any], voices_dir: str | None = None) -> None:
        super().__init__(config, voices_dir)
        self._model: Any = None

    async def _load(self) -> None:
        def load() -> Any:
            try:
                import onnx_asr
            except ImportError as exc:
                raise BackendUnavailable(
                    "Install Parakeet support with: pip install 'timbre-voice[parakeet]'"
                ) from exc

            model_name = str(self.config.get("model", "parakeet-tdt-0.6b-v3")).lower()
            cfg = MODEL_CONFIGS.get(model_name, MODEL_CONFIGS["parakeet-tdt-0.6b-v3"])
            providers = _providers(self.config.get("device", "cpu"))
            sess_options = _session_options(self.config)
            kwargs: dict[str, Any] = {
                "quantization": self.config.get("quantization", cfg["quantization"]),
                "providers": providers,
                "sess_options": sess_options,
            }
            model = onnx_asr.load_model(cfg["hf_id"], **kwargs)
            if bool(self.config.get("timestamps", False)) and hasattr(model, "with_timestamps"):
                model = model.with_timestamps()
            return model

        self._model = await asyncio.to_thread(load)

    async def transcribe(self, audio: bytes, **opts: Any) -> str:
        await self.ensure_loaded()

        def run() -> str:
            waveform = _load_audio(audio)
            results = self._model.recognize([waveform])
            result = results[0] if isinstance(results, list) else results
            return _clean_text(getattr(result, "text", str(result)))

        return await asyncio.to_thread(run)

    async def _unload(self) -> None:
        self._model = None


def _providers(device: str) -> list[Any]:
    try:
        import onnxruntime as ort
    except ImportError as exc:
        raise BackendUnavailable(
            "Install ONNX Runtime with: pip install 'timbre-voice[parakeet]'"
        ) from exc

    available = ort.get_available_providers()
    if device.startswith("cuda") and "CUDAExecutionProvider" in available:
        return [
            (
                "CUDAExecutionProvider",
                {
                    "device_id": _device_index(device),
                    "cudnn_conv_algo_search": "EXHAUSTIVE",
                    "cudnn_conv_use_max_workspace": "1",
                    "do_copy_in_default_stream": True,
                },
            ),
            "CPUExecutionProvider",
        ]
    return ["CPUExecutionProvider"]


def _session_options(config: dict[str, Any]) -> Any:
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.intra_op_num_threads = int(config.get("ort_intra_threads", 1))
    options.inter_op_num_threads = int(config.get("ort_inter_threads", 1))
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    options.add_session_config_entry("session.set_denormal_as_zero", "1")
    options.add_session_config_entry("session.intra_op.allow_spinning", "1")
    options.add_session_config_entry("session.inter_op.allow_spinning", "0")
    return options


def _load_audio(data: bytes) -> np.ndarray:
    info = _wav_info(data)
    if info is not None:
        wav = _decode_pcm_wav(data, info)
        if wav is not None:
            return wav
    return _ffmpeg_decode(data)


def _wav_info(data: bytes) -> dict[str, Any] | None:
    try:
        with wave.open(BytesIO(data), "rb") as wav:
            return {
                "frames": wav.getnframes(),
                "sample_rate": wav.getframerate(),
                "channels": wav.getnchannels(),
                "sample_width": wav.getsampwidth(),
                "compression": wav.getcomptype(),
            }
    except (wave.Error, EOFError, OSError):
        return None


def _decode_pcm_wav(data: bytes, info: dict[str, Any]) -> np.ndarray | None:
    if info["compression"] != "NONE":
        return None
    sample_width = int(info["sample_width"])
    channels = int(info["channels"])
    if sample_width not in (1, 2, 3, 4) or channels not in (1, 2):
        return None
    try:
        with wave.open(BytesIO(data), "rb") as wav:
            pcm = wav.readframes(wav.getnframes())
        if channels == 2:
            pcm = audioop.tomono(pcm, sample_width, 0.5, 0.5)
            channels = 1
        if int(info["sample_rate"]) != TARGET_SR:
            pcm, _state = audioop.ratecv(
                pcm, sample_width, channels, int(info["sample_rate"]), TARGET_SR, None
            )
        if sample_width == 1:
            return (np.frombuffer(pcm, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
        if sample_width == 2:
            return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        if sample_width == 4:
            return np.frombuffer(pcm, dtype="<i4").astype(np.float32) / 2147483648.0
        pcm16 = audioop.lin2lin(pcm, sample_width, 2)
        return np.frombuffer(pcm16, dtype="<i2").astype(np.float32) / 32768.0
    except (wave.Error, EOFError, OSError, audioop.error, ValueError):
        return None


def _ffmpeg_decode(data: bytes) -> np.ndarray:
    command = [
        "ffmpeg",
        "-nostdin",
        "-loglevel",
        "error",
        "-i",
        "pipe:0",
        "-ac",
        "1",
        "-ar",
        str(TARGET_SR),
        "-f",
        "s16le",
        "pipe:1",
    ]
    process = subprocess.run(command, input=data, capture_output=True, check=False)
    if process.returncode != 0:
        stderr = process.stderr.decode(errors="ignore")[:300]
        raise BackendUnavailable(f"Parakeet audio decode failed: {stderr}")
    return np.frombuffer(process.stdout, dtype="<i2").astype(np.float32) / 32768.0


def _clean_text(text: str) -> str:
    text = text.replace("\u2581", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text.replace(" '", "'")


def _device_index(device: str) -> int:
    if ":" not in device:
        return 0
    try:
        return int(device.split(":", 1)[1])
    except ValueError:
        return 0
