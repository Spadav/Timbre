from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from huggingface_hub import snapshot_download, try_to_load_from_cache

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
        *_pocket_profiles(root),
        ModelProfile(
            id="supertonic:supertonic-3",
            backend="supertonic",
            kind="tts",
            label="Supertonic 3",
            path=root / "supertonic" / "supertonic-3",
            options={"model": "supertonic-3", "model_path": str(root / "supertonic" / "supertonic-3")},
        ),
        ModelProfile(
            id="qwen3:0.6b-base",
            backend="qwen3",
            kind="tts",
            label="Qwen3 TTS 0.6B Base",
            path=root / "qwen3" / "0.6b-base",
            repo_id="Qwen/Qwen3-TTS-12Hz-0.6B-Base",
            options={
                "model": "0.6b-base",
                "repo_id": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
                "model_type": "base",
                "model_path": str(root / "qwen3" / "0.6b-base"),
            },
            downloadable=True,
        ),
        ModelProfile(
            id="qwen3:0.6b-customvoice",
            backend="qwen3",
            kind="tts",
            label="Qwen3 TTS 0.6B CustomVoice",
            path=root / "qwen3" / "0.6b-customvoice",
            repo_id="Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
            options={
                "model": "0.6b-customvoice",
                "repo_id": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
                "model_type": "customvoice",
                "model_path": str(root / "qwen3" / "0.6b-customvoice"),
            },
            downloadable=True,
        ),
        ModelProfile(
            id="qwen3:1.7b-base",
            backend="qwen3",
            kind="tts",
            label="Qwen3 TTS 1.7B Base",
            path=root / "qwen3" / "1.7b-base",
            repo_id="Qwen/Qwen3-TTS-12Hz-1.7B-Base",
            options={
                "model": "1.7b-base",
                "repo_id": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
                "model_type": "base",
                "model_path": str(root / "qwen3" / "1.7b-base"),
            },
            downloadable=True,
        ),
        ModelProfile(
            id="qwen3:1.7b-voicedesign",
            backend="qwen3",
            kind="tts",
            label="Qwen3 TTS 1.7B VoiceDesign",
            path=root / "qwen3" / "1.7b-voicedesign",
            repo_id="Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
            options={
                "model": "1.7b-voicedesign",
                "repo_id": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
                "model_type": "voice_design",
                "model_path": str(root / "qwen3" / "1.7b-voicedesign"),
            },
            downloadable=True,
        ),
        ModelProfile(
            id="qwen3:1.7b-customvoice",
            backend="qwen3",
            kind="tts",
            label="Qwen3 TTS 1.7B CustomVoice",
            path=root / "qwen3" / "1.7b-customvoice",
            repo_id="Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
            options={
                "model": "1.7b-customvoice",
                "repo_id": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
                "model_type": "customvoice",
                "model_path": str(root / "qwen3" / "1.7b-customvoice"),
            },
            downloadable=True,
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
    backend.enabled = True
    group.default = profile.backend
    return config


def download_model(profile_id: str) -> Path:
    profile = get_profile(profile_id)
    profile.path.mkdir(parents=True, exist_ok=True)
    if profile.backend == "supertonic":
        return profile.path
    if profile.backend == "pocket":
        return _download_pocket_model(profile)
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
    if profile.backend == "pocket":
        return _pocket_profile_installed(profile)
    return profile.path.exists() and any(profile.path.iterdir())


def _profile_active(config: TimbreConfig, profile: ModelProfile) -> bool:
    group = config.tts if profile.kind == "tts" else config.stt
    backend = group.backends.get(profile.backend)
    if backend is None:
        return False
    if profile.backend == "pocket":
        active_language = backend.options.get("language") or backend.options.get("model") or "english"
        return active_language == profile.options.get("language")
    return all(
        backend.options.get(key) == value
        for key, value in profile.options.items()
        if key != "model_path"
    )


def _pocket_profiles(root: Path) -> list[ModelProfile]:
    models = [
        ("english", "PocketTTS English (latest alias)"),
        ("english_2026-04", "PocketTTS English 2026-04"),
        ("english_2026-01", "PocketTTS English 2026-01"),
        ("italian", "PocketTTS Italian"),
        ("italian_24l", "PocketTTS Italian 24L"),
        ("german", "PocketTTS German"),
        ("german_24l", "PocketTTS German 24L"),
        ("spanish", "PocketTTS Spanish"),
        ("spanish_24l", "PocketTTS Spanish 24L"),
        ("portuguese", "PocketTTS Portuguese"),
        ("portuguese_24l", "PocketTTS Portuguese 24L"),
        ("french_24l", "PocketTTS French 24L"),
    ]
    return [
        ModelProfile(
            id=f"pocket:{model}",
            backend="pocket",
            kind="tts",
            label=label,
            path=root / "pocket" / model,
            options={"model": model, "language": model},
            downloadable=True,
        )
        for model, label in models
    ]


def _download_pocket_model(profile: ModelProfile) -> Path:
    from pocket_tts.utils.utils import download_if_necessary

    language = str(profile.options["language"])
    config = _pocket_config(language)
    refs = [
        config.get("weights_path"),
        config.get("weights_path_without_voice_cloning"),
        (config.get("flow_lm") or {}).get("lookup_table", {}).get("tokenizer_path"),
    ]
    for ref in refs:
        if ref:
            download_if_necessary(str(ref))
    profile.path.mkdir(parents=True, exist_ok=True)
    marker = profile.path / ".downloaded"
    marker.write_text("Downloaded through PocketTTS cache.\n", encoding="utf-8")
    return profile.path


def _pocket_profile_installed(profile: ModelProfile) -> bool:
    if profile.path.exists() and any(profile.path.iterdir()):
        return True
    try:
        config = _pocket_config(str(profile.options["language"]))
    except Exception:
        return False
    tokenizer = (config.get("flow_lm") or {}).get("lookup_table", {}).get("tokenizer_path")
    weights = [config.get("weights_path"), config.get("weights_path_without_voice_cloning")]
    return bool(tokenizer and _hf_ref_cached(tokenizer)) and any(
        _hf_ref_cached(ref) for ref in weights if ref
    )


def _pocket_config(language: str) -> dict[str, Any]:
    import pocket_tts

    path = Path(pocket_tts.__file__).parent / "config" / f"{language}.yaml"
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _hf_ref_cached(ref: str) -> bool:
    if not ref.startswith("hf://"):
        return Path(ref).exists()
    repo_id, filename, revision = _parse_hf_ref(ref)
    cached = try_to_load_from_cache(repo_id=repo_id, filename=filename, revision=revision)
    return isinstance(cached, str)


def _parse_hf_ref(ref: str) -> tuple[str, str, str | None]:
    path = ref.removeprefix("hf://")
    parts = path.split("/")
    repo_id = "/".join(parts[:2])
    filename = "/".join(parts[2:])
    revision = None
    if "@" in filename:
        filename, revision = filename.split("@", 1)
    return repo_id, filename, revision
