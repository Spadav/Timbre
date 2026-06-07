from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from timbre.audio import convert_audio, media_type_for
from timbre.errors import BackendUnavailable, UnknownBackend

router = APIRouter()


class SpeechRequest(BaseModel):
    model: str | None = None
    input: str = Field(min_length=1)
    voice: str = "default"
    response_format: str = "wav"
    speed: float | None = None


@router.post("/v1/audio/speech")
async def speech(payload: SpeechRequest, request: Request) -> Response:
    manager = request.app.state.manager
    try:
        backend = await manager.get_tts(payload.model)
        opts: dict[str, Any] = {"response_format": "wav"}
        if payload.speed is not None:
            opts["speed"] = payload.speed
        audio = await backend.synthesize(payload.input, payload.voice, **opts)
        fmt = payload.response_format.lower()
        if fmt != "wav":
            audio = convert_audio(audio, "wav", fmt)
        return Response(content=audio, media_type=media_type_for(fmt))
    except UnknownBackend as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except BackendUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


