from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from timbre.audio import convert_audio, media_type_for
from timbre.backends.tts.qwen3 import DEFAULT_QWEN3_VOICES
from timbre.config import CONFIG_DIR, CONFIG_PATH, TimbreConfig, dump_config
from timbre.errors import BackendUnavailable, UnknownBackend
from timbre.manager import BackendManager
from timbre.models import set_active_model
from timbre.voices.store import SAFE_NAME, VoiceStore

router = APIRouter(prefix="/v1/qwen")

QWEN_VOICES_DIR = CONFIG_DIR / "qwen" / "voices"


class QwenCloneSpeechRequest(BaseModel):
    input: str = Field(min_length=1)
    voice: str = Field(min_length=1)
    model_size: Literal["0.6b", "1.7b"] = "1.7b"
    response_format: str = "wav"
    speed: float = 1.0
    language: str = "Auto"
    x_vector_only_mode: bool | None = None


class QwenCustomVoiceSpeechRequest(BaseModel):
    input: str = Field(min_length=1)
    speaker: str = "Vivian"
    model_size: Literal["0.6b", "1.7b"] = "1.7b"
    instruct: str | None = None
    response_format: str = "wav"
    speed: float = 1.0
    language: str = "Auto"


class QwenVoiceDesignSpeechRequest(BaseModel):
    input: str = Field(min_length=1)
    instruct: str = Field(min_length=1)
    model_size: Literal["1.7b"] = "1.7b"
    response_format: str = "wav"
    speed: float = 1.0
    language: str = "Auto"


class QwenDesignSaveRequest(BaseModel):
    name: str = Field(min_length=1)
    input: str = Field(min_length=1)
    instruct: str = Field(min_length=1)
    model_size: Literal["1.7b"] = "1.7b"
    speed: float = 1.0
    language: str = "Auto"


@router.get("/voices")
async def qwen_voices(request: Request) -> dict[str, object]:
    store = _qwen_store(request)
    clones = [
        {
            "name": record.name,
            "type": "clone",
            "audio_path": str(record.audio_path) if record.audio_path else None,
            "ref_text": _read_text(record.path / "reference.txt"),
            "design": _read_text(record.path / "design.txt"),
            "prepared": _is_prepared(request, record.name),
        }
        for record in store.list()
    ]
    presets = [{"name": name, "type": "preset"} for name in sorted(DEFAULT_QWEN3_VOICES)]
    return {
        "object": "list",
        "data": {"clones": clones, "presets": presets},
    }


@router.post("/voices")
async def create_qwen_voice(
    request: Request,
    name: str = Form(...),
    file: UploadFile = File(...),
    ref_text: str = Form(default=""),
    design: str = Form(default=""),
    prepare: bool = Form(default=False),
    model_size: Literal["0.6b", "1.7b"] = Form(default="1.7b"),
) -> dict[str, object]:
    try:
        record = await _qwen_store(request).save_upload(name, file)
        _write_text(record.path / "reference.txt", ref_text)
        _write_text(record.path / "design.txt", design)
        prepared = await _prepare_record(request, record.name, model_size=model_size) if prepare else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except UnknownBackend as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except BackendUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "name": record.name,
        "path": str(record.path),
        "audio_path": str(record.audio_path),
        "prepared": prepared,
    }


@router.get("/voices/{name}/reference")
async def qwen_voice_reference(request: Request, name: str) -> Response:
    record = _qwen_store(request).get(name)
    if record is None or record.audio_path is None or not record.audio_path.is_file():
        raise HTTPException(status_code=404, detail=f"Qwen voice '{name}' has no reference audio.")
    fmt = record.audio_path.suffix.lower().lstrip(".")
    return Response(content=record.audio_path.read_bytes(), media_type=media_type_for(fmt))


@router.post("/voices/{name}/prepare")
async def prepare_qwen_voice(
    request: Request,
    name: str,
    model_size: Literal["0.6b", "1.7b"] = Query(default="1.7b"),
) -> dict[str, object]:
    try:
        prepared = await _prepare_record(request, name, model_size=model_size)
    except UnknownBackend as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except BackendUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"name": name, "prepared": prepared}


@router.delete("/voices/{name}")
async def delete_qwen_voice(request: Request, name: str) -> dict[str, object]:
    deleted = _qwen_store(request).delete(name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Qwen voice '{name}' not found.")
    return {"deleted": True, "name": name}


@router.post("/clone/speech")
async def qwen_clone_speech(payload: QwenCloneSpeechRequest, request: Request) -> Response:
    record = _qwen_store(request).get(payload.voice)
    if record is None or record.audio_path is None:
        raise HTTPException(status_code=404, detail=f"Unknown Qwen clone voice '{payload.voice}'.")
    try:
        await _ensure_qwen_model(request, "base", payload.model_size)
        backend = await request.app.state.manager.get_tts("qwen3")
        audio = await backend.synthesize_clone(
            payload.input,
            record.audio_path,
            language=payload.language,
            speed=payload.speed,
            ref_text=_read_text(record.path / "reference.txt"),
            x_vector_only_mode=payload.x_vector_only_mode,
        )
        return _audio_response(audio, payload.response_format)
    except UnknownBackend as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except BackendUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/custom-voice/speech")
async def qwen_custom_voice_speech(payload: QwenCustomVoiceSpeechRequest, request: Request) -> Response:
    try:
        await _ensure_qwen_model(request, "customvoice", payload.model_size)
        backend = await request.app.state.manager.get_tts("qwen3")
        audio = await backend.synthesize_custom_voice(
            payload.input,
            payload.speaker,
            language=payload.language,
            instruct=payload.instruct,
            speed=payload.speed,
        )
        return _audio_response(audio, payload.response_format)
    except UnknownBackend as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except BackendUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/voice-design/speech")
async def qwen_voice_design_speech(payload: QwenVoiceDesignSpeechRequest, request: Request) -> Response:
    try:
        await _ensure_qwen_model(request, "voice_design", payload.model_size)
        backend = await request.app.state.manager.get_tts("qwen3")
        audio = await backend.synthesize_voice_design(
            payload.input,
            payload.instruct,
            language=payload.language,
            speed=payload.speed,
        )
        return _audio_response(audio, payload.response_format)
    except UnknownBackend as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except BackendUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/voice-design/save")
async def save_qwen_voice_design(payload: QwenDesignSaveRequest, request: Request) -> dict[str, object]:
    try:
        await _ensure_qwen_model(request, "voice_design", payload.model_size)
        backend = await request.app.state.manager.get_tts("qwen3")
        audio = await backend.synthesize_voice_design(
            payload.input,
            payload.instruct,
            language=payload.language,
            speed=payload.speed,
        )
        store = _qwen_store(request)
        if not SAFE_NAME.match(payload.name):
            raise ValueError("Voice name must be 1-80 chars: letters, numbers, dot, dash, underscore.")
        path = store.root / payload.name
        path.mkdir(parents=True, exist_ok=True)
        audio_path = path / "reference.wav"
        audio_path.write_bytes(audio)
        _write_text(path / "reference.txt", payload.input)
        _write_text(path / "design.txt", payload.instruct)
        return {
            "name": payload.name,
            "path": str(path),
            "audio_path": str(audio_path),
            "ref_text": payload.input,
            "design": payload.instruct,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except UnknownBackend as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except BackendUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _qwen_store(request: Request) -> VoiceStore:
    store = getattr(request.app.state, "qwen_voice_store", None)
    if store is None:
        store = VoiceStore(QWEN_VOICES_DIR)
        request.app.state.qwen_voice_store = store
    return store


async def _prepare_record(
    request: Request,
    name: str,
    *,
    model_size: Literal["0.6b", "1.7b"] = "1.7b",
) -> dict[str, str]:
    record = _qwen_store(request).get(name)
    if record is None or record.audio_path is None:
        raise HTTPException(status_code=404, detail=f"Qwen voice '{name}' has no reference audio.")
    await _ensure_qwen_model(request, "base", model_size)
    backend = await request.app.state.manager.get_tts("qwen3")
    prepared = await backend.prepare_clone_reference(
        record.name,
        record.audio_path,
        ref_text=_read_text(record.path / "reference.txt"),
    )
    return prepared


def _is_prepared(request: Request, name: str) -> bool:
    manager = request.app.state.manager
    backend = manager.tts.get("qwen3")
    cache = getattr(backend, "_voice_prompt_cache", {}) if backend else {}
    return any(str(key).startswith(f"{name}:") for key in cache)


async def _ensure_qwen_model(
    request: Request,
    model_type: Literal["base", "customvoice", "voice_design"],
    model_size: Literal["0.6b", "1.7b"] = "1.7b",
) -> None:
    config = request.app.state.config
    backend = config.tts.backends.get("qwen3")
    if backend is None:
        raise UnknownBackend("Qwen3 backend is not configured.")
    if (
        backend.options.get("model_type") == model_type
        and str(backend.options.get("model", "")).startswith(model_size)
        and backend.enabled
    ):
        return

    profile_id = _preferred_qwen_profile(model_type, model_size)
    config = set_active_model(config, profile_id)
    await _replace_config(request, config)


def _preferred_qwen_profile(
    model_type: Literal["base", "customvoice", "voice_design"],
    model_size: Literal["0.6b", "1.7b"],
) -> str:
    if model_type == "voice_design":
        return "qwen3:1.7b-voicedesign"

    suffix = "base" if model_type == "base" else "customvoice"
    return f"qwen3:{model_size}-{suffix}"


async def _replace_config(request: Request, config: TimbreConfig) -> None:
    config_path = Path(getattr(request.app.state, "config_path", CONFIG_PATH))
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(dump_config(config), handle, sort_keys=False)

    old_manager = request.app.state.manager
    try:
        if old_manager.tts.get("qwen3") is not None:
            await old_manager.unload_backend("tts", "qwen3")
    except (BackendUnavailable, UnknownBackend):
        pass
    await old_manager.stop_sweeper()

    manager = BackendManager(config)
    request.app.state.config = config
    request.app.state.manager = manager
    request.app.state.voice_store = VoiceStore(Path(config.voices.dir))
    request.app.state.qwen_voice_store = VoiceStore(QWEN_VOICES_DIR)
    manager.start_sweeper()


def _audio_response(audio: bytes, response_format: str) -> Response:
    fmt = response_format.lower()
    if fmt != "wav":
        audio = convert_audio(audio, "wav", fmt)
    return Response(content=audio, media_type=media_type_for(fmt))


def _read_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text or None


def _write_text(path: Path, text: str | None) -> None:
    clean = (text or "").strip()
    if clean:
        path.write_text(clean, encoding="utf-8")
    elif path.exists():
        path.unlink()
