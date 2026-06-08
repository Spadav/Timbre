from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException, Request

from timbre.config import CONFIG_PATH, dump_config, parse_config
from timbre.manager import BackendManager
from timbre.voices.store import VoiceStore

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


@router.get("/v1/config")
async def get_config(request: Request) -> dict[str, object]:
    return {
        "path": str(getattr(request.app.state, "config_path", CONFIG_PATH)),
        "config": dump_config(request.app.state.config),
    }


@router.put("/v1/config")
async def update_config(payload: dict[str, Any], request: Request) -> dict[str, object]:
    try:
        config = parse_config(payload)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    config_path = Path(getattr(request.app.state, "config_path", CONFIG_PATH))
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(dump_config(config), handle, sort_keys=False)

    old_manager = request.app.state.manager
    await old_manager.stop_sweeper()
    manager = BackendManager(config)
    request.app.state.config = config
    request.app.state.manager = manager
    request.app.state.voice_store = VoiceStore(Path(config.voices.dir))
    manager.start_sweeper()

    return {"path": str(config_path), "config": dump_config(config)}
