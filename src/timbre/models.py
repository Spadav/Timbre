from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from huggingface_hub import snapshot_download

from timbre.config import CONFIG_DIR, TimbreConfig

ModelKind = Literal["tts", "stt"]


@dataclass(frozen=True, slots=True)
class ModelProfile:
    id: str
    backend: str
    kind: ModelKind
    label: str
    path: Path
    options: dict[str, Any]
    repo_id: str | None = None
    downloadable: bool = False


def model_profiles() -> list[ModelProfile]:
    root = CONFIG_DIR / "models"
    return [
        ModelProfile(
            id="pocket:default",
            backend="pocket",
            kind="tts",
            label="PocketTTS default",
            path=root / "pocket" / "default",
            options={},
        ),
        ModelProfile(
            id="supertonic:supertonic-3",
            backend="supertonic",
            kind="tts",
            label="Supertonic 3",
            path=root / "supertonic" / "supertonic-3",
            options={"model": "supertonic-3", "model_path": str(root / "supertonic" / "supertonic-3")},
        ),
        ModelProfile(
            id="whisper:tiny",
            backend="whisper",
            kind="stt",
            label="Whisper tiny",
            path=root / "whisper" / "tiny",
            options={"model_size": "tiny", "model_path": str(root / "whisper" / "tiny")},
            downloadable=True,
        ),
        ModelProfile(
            id="whisper:base",
            backend="whisper",
            kind="stt",
            label="Whisper base",
            path=root / "whisper" / "base",
            options={"model_size": "base", "model_path": str(root / "whisper" / "base")},
            downloadable=True,
        ),
        ModelProfile(
            id="whisper:small",
            backend="whisper",
            kind="stt",
            label="Whisper small",
            path=root / "whisper" / "small",
            options={"model_size": "small", "model_path": str(root / "whisper" / "small")},
            downloadable=True,
        ),
        ModelProfile(
            id="whisper:medium",
            backend="whisper",
            kind="stt",
            label="Whisper medium",
            path=root / "whisper" / "medium",
            options={"model_size": "medium", "model_path": str(root / "whisper" / "medium")},
            downloadable=True,
        ),
        ModelProfile(
            id="whisper:large-v3",
            backend="whisper",
            kind="stt",
            label="Whisper large-v3",
            path=root / "whisper" / "large-v3",
            options={"model_size": "large-v3", "model_path": str(root / "whisper" / "large-v3")},
            downloadable=True,
        ),
        ModelProfile(
            id="parakeet:int8",
            backend="parakeet",
            kind="stt",
            label="Parakeet CPU INT8",
            path=root / "parakeet" / "int8",
            repo_id="nemo-parakeet-tdt-0.6b-v3",
            options={
                "model": "parakeet-tdt-0.6b-v3",
                "repo_id": "nemo-parakeet-tdt-0.6b-v3",
                "quantization": "int8",
                "model_path": str(root / "parakeet" / "int8"),
            },
            downloadable=True,
        ),
        ModelProfile(
            id="parakeet:fp32",
            backend="parakeet",
            kind="stt",
            label="Parakeet FP32",
            path=root / "parakeet" / "fp32",
            repo_id="istupakov/parakeet-tdt-0.6b-v3-onnx",
            options={
                "model": "istupakov/parakeet-tdt-0.6b-v3-onnx",
                "repo_id": "istupakov/parakeet-tdt-0.6b-v3-onnx",
                "quantization": None,
                "model_path": str(root / "parakeet" / "fp32"),
            },
            downloadable=True,
        ),
        ModelProfile(
            id="parakeet:fp16",
            backend="parakeet",
            kind="stt",
            label="Parakeet FP16",
            path=root / "parakeet" / "fp16",
            repo_id="grikdotnet/parakeet-tdt-0.6b-fp16",
            options={
                "model": "grikdotnet/parakeet-tdt-0.6b-fp16",
                "repo_id": "grikdotnet/parakeet-tdt-0.6b-fp16",
                "quantization": "fp16",
                "model_path": str(root / "parakeet" / "fp16"),
            },
            downloadable=True,
        ),
    ]


def get_profile(profile_id: str) -> ModelProfile:
    for profile in model_profiles():
        if profile.id == profile_id:
            return profile
    raise ValueError(f"Unknown model profile '{profile_id}'.")


def model_records(config: TimbreConfig) -> list[dict[str, Any]]:
    return [
        {
            "id": profile.id,
            "object": "model",
            "kind": profile.kind,
            "backend": profile.backend,
            "label": profile.label,
            "path": str(profile.path),
            "downloadable": profile.downloadable,
            "installed": _profile_installed(profile),
            "active": _profile_active(config, profile),
        }
        for profile in model_profiles()
    ]


def set_active_model(config: TimbreConfig, profile_id: str) -> TimbreConfig:
    profile = get_profile(profile_id)
    group = config.tts if profile.kind == "tts" else config.stt
    backend = group.backends.get(profile.backend)
    if backend is None:
        raise ValueError(f"Backend '{profile.backend}' is not configured.")
    backend.options.update(profile.options)
    group.default = profile.backend
    return config


def download_model(profile_id: str) -> Path:
    profile = get_profile(profile_id)
    profile.path.mkdir(parents=True, exist_ok=True)
    if profile.backend == "supertonic":
        return profile.path
    if profile.backend == "whisper":
        from faster_whisper.utils import download_model as download_whisper_model

        return Path(
            download_whisper_model(
                str(profile.options["model_size"]),
                output_dir=str(profile.path),
            )
        )
    if profile.repo_id:
        return Path(snapshot_download(repo_id=profile.repo_id, local_dir=profile.path))
    return profile.path


def _profile_installed(profile: ModelProfile) -> bool:
    if not profile.downloadable:
        return True
    return profile.path.exists() and any(profile.path.iterdir())


def _profile_active(config: TimbreConfig, profile: ModelProfile) -> bool:
    group = config.tts if profile.kind == "tts" else config.stt
    backend = group.backends.get(profile.backend)
    if backend is None or group.default != profile.backend:
        return False
    return all(
        backend.options.get(key) == value
        for key, value in profile.options.items()
        if key != "model_path"
    )
