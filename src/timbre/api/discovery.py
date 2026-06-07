from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "timbre"}


@router.get("/v1/backends")
async def backends(request: Request) -> dict[str, list[dict[str, object]]]:
    manager = request.app.state.manager
    return {
        "data": [
            {
                "name": state.name,
                "kind": state.kind,
                "enabled": state.enabled,
                "loaded": state.loaded,
                "ttl": state.ttl,
                "device": state.device,
            }
            for state in manager.list_states()
        ]
    }


@router.get("/v1/models")
async def models(request: Request) -> dict[str, object]:
    return {"object": "list", "data": request.app.state.manager.model_records()}


@router.get("/v1/voices")
async def voices(request: Request) -> dict[str, object]:
    store = request.app.state.voice_store
    cloned = [
        {
            "name": record.name,
            "type": "cloned",
            "audio_path": str(record.audio_path) if record.audio_path else None,
            "prepared_backends": sorted(_backend_from_cache(path.name) for path in record.caches),
        }
        for record in store.list()
    ]
    cloned_names = {record["name"] for record in cloned}
    presets = [
        {"name": voice, "backend": backend, "type": "preset"}
        for backend, voices_for_backend in request.app.state.manager.all_voices().items()
        for voice in voices_for_backend
        if voice not in cloned_names
    ]
    return {"object": "list", "data": presets + cloned}


def _backend_from_cache(filename: str) -> str:
    return filename.split(".", 1)[0]
