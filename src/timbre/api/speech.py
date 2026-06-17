from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from timbre.audio import convert_audio, media_type_for
from timbre.api.qwen import _ensure_qwen_model, _qwen_store, _read_text
from timbre.errors import BackendUnavailable, UnknownBackend

router = APIRouter()


class SpeechRequest(BaseModel):
    model: str | None = None
    input: str = Field(min_length=1)
    voice: str = "default"
    response_format: str = "wav"
    speed: float | None = None
    language: str | None = None
    lang: str | None = None
    steps: int | None = None
    qwen_mode: Literal["auto", "clone", "preset", "custom_voice", "customvoice"] = "auto"
    model_size: Literal["0.6b", "1.7b"] = "0.6b"
    instruct: str | None = None
    instructions: str | None = None
    x_vector_only_mode: bool | None = None


@router.post("/v1/audio/speech")
async def speech(payload: SpeechRequest, request: Request) -> Response:
    manager = request.app.state.manager
    try:
        backend_name = manager.resolve_tts_name(payload.model)
        if backend_name == "qwen3":
            return await _qwen_speech(payload, request)

        backend = await manager.get_tts(payload.model)
        voice = manager.resolve_tts_voice(backend_name, payload.voice)
        opts: dict[str, Any] = {"response_format": "wav"}
        if payload.speed is not None:
            opts["speed"] = payload.speed
        if payload.language is not None:
            opts["lang"] = payload.language
        if payload.lang is not None:
            opts["lang"] = payload.lang
        if payload.steps is not None:
            opts["steps"] = payload.steps
        audio = await backend.synthesize(payload.input, voice, **opts)
        fmt = payload.response_format.lower()
        if fmt != "wav":
            audio = convert_audio(audio, "wav", fmt)
        return Response(content=audio, media_type=media_type_for(fmt))
    except UnknownBackend as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except BackendUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


async def _qwen_speech(payload: SpeechRequest, request: Request) -> Response:
    manager = request.app.state.manager
    voice = manager.resolve_tts_voice("qwen3", payload.voice)
    mode = "preset" if payload.qwen_mode in {"preset", "custom_voice", "customvoice"} else payload.qwen_mode
    record = _qwen_store(request).get(voice)

    if mode == "auto":
        mode = "clone" if record is not None and record.audio_path is not None else "preset"

    language = payload.lang or payload.language or "Auto"
    speed = payload.speed if payload.speed is not None else 1.0

    try:
        if mode == "clone":
            if record is None or record.audio_path is None:
                raise HTTPException(status_code=404, detail=f"Unknown Qwen clone voice '{voice}'.")
            await _ensure_qwen_model(request, "base", payload.model_size)
            backend = await request.app.state.manager.get_tts("qwen3")
            audio = await backend.synthesize_clone(
                payload.input,
                record.audio_path,
                language=language,
                speed=speed,
                ref_text=_read_text(record.path / "reference.txt"),
                x_vector_only_mode=payload.x_vector_only_mode,
            )
        else:
            await _ensure_qwen_model(request, "customvoice", payload.model_size)
            backend = await request.app.state.manager.get_tts("qwen3")
            audio = await backend.synthesize_custom_voice(
                payload.input,
                voice,
                language=language,
                instruct=payload.instruct or payload.instructions,
                speed=speed,
            )
        fmt = payload.response_format.lower()
        if fmt != "wav":
            audio = convert_audio(audio, "wav", fmt)
        return Response(content=audio, media_type=media_type_for(fmt))
    except UnknownBackend as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except BackendUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
