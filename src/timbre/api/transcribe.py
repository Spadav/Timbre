from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from timbre.errors import BackendUnavailable, UnknownBackend
from timbre.eventlog import Timer, client_host, event_log

router = APIRouter()


@router.post("/v1/audio/transcriptions")
async def transcriptions(
    request: Request,
    file: UploadFile = File(...),
    model: str | None = Form(default=None),
    language: str | None = Form(default=None),
    prompt: str | None = Form(default=None),
) -> dict[str, str]:
    manager = request.app.state.manager
    log = event_log(request)
    timer = Timer()
    backend_name = model or request.app.state.config.stt.default
    log.add(
        kind="stt",
        operation="transcription",
        status="start",
        message="transcription request received",
        backend=backend_name,
        model=model,
        format=_suffix(file.filename),
        client=client_host(request),
    )
    try:
        backend = await manager.get_stt(model)
        audio = await file.read()
        opts = {"suffix": _suffix(file.filename)}
        if language:
            opts["language"] = language
        if prompt:
            opts["initial_prompt"] = prompt
        text = await backend.transcribe(audio, **opts)
        log.add(
            kind="stt",
            operation="transcription",
            status="ok",
            message="audio transcribed",
            backend=backend_name,
            model=model,
            format=opts["suffix"],
            input_chars=len(audio),
            output_bytes=len(text.encode("utf-8")),
            duration=timer.seconds,
            client=client_host(request),
        )
        return {"text": text}
    except UnknownBackend as exc:
        log.add(
            level="error",
            kind="stt",
            operation="transcription",
            status="error",
            message=str(exc),
            backend=backend_name,
            model=model,
            duration=timer.seconds,
            client=client_host(request),
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except BackendUnavailable as exc:
        log.add(
            level="error",
            kind="stt",
            operation="transcription",
            status="error",
            message=str(exc),
            backend=backend_name,
            model=model,
            duration=timer.seconds,
            client=client_host(request),
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _suffix(filename: str | None) -> str:
    if not filename or "." not in filename:
        return ".wav"
    return "." + filename.rsplit(".", 1)[1].lower()
