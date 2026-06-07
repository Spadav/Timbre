from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

router = APIRouter()


@router.post("/v1/voices")
async def create_voice(
    request: Request,
    name: str = Form(...),
    file: UploadFile = File(...),
) -> dict[str, object]:
    try:
        record = await request.app.state.voice_store.save_upload(name, file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"name": record.name, "path": str(record.path), "audio_path": str(record.audio_path)}


@router.delete("/v1/voices/{name}")
async def delete_voice(request: Request, name: str) -> dict[str, object]:
    deleted = request.app.state.voice_store.delete(name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Voice '{name}' not found.")
    return {"deleted": True, "name": name}
