from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from timbre.audio import media_type_for
from timbre.errors import BackendUnavailable, UnknownBackend

router = APIRouter()


@router.post("/v1/voices")
async def create_voice(
    request: Request,
    name: str = Form(...),
    file: UploadFile = File(...),
    backend: str | None = Form(default=None),
    precompute: bool = Form(default=True),
) -> dict[str, object]:
    try:
        record = await request.app.state.voice_store.save_upload(name, file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    prepared: list[dict[str, str]] = []
    if precompute:
        try:
            prepared = await request.app.state.manager.prepare_voice_clone(name, backend)
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


@router.get("/v1/voices/{name}/reference")
async def voice_reference(request: Request, name: str) -> Response:
    record = request.app.state.voice_store.get(name)
    if record is None or record.audio_path is None or not record.audio_path.is_file():
        raise HTTPException(status_code=404, detail=f"Voice '{name}' has no reference audio.")
    fmt = record.audio_path.suffix.lower().lstrip(".")
    return Response(content=record.audio_path.read_bytes(), media_type=media_type_for(fmt))


@router.delete("/v1/voices/{name}")
async def delete_voice(request: Request, name: str) -> dict[str, object]:
    deleted = request.app.state.voice_store.delete(name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Voice '{name}' not found.")
    return {"deleted": True, "name": name}
