from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from timbre.errors import BackendUnavailable, UnknownBackend

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
    try:
        backend = await manager.get_stt(model)
        audio = await file.read()
        opts = {"suffix": _suffix(file.filename)}
        if language:
            opts["language"] = language
        if prompt:
            opts["initial_prompt"] = prompt
        text = await backend.transcribe(audio, **opts)
        return {"text": text}
    except UnknownBackend as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except BackendUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _suffix(filename: str | None) -> str:
    if not filename or "." not in filename:
        return ".wav"
    return "." + filename.rsplit(".", 1)[1].lower()
