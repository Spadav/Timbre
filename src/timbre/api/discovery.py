from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from timbre.config import CONFIG_PATH, BackendGroupConfig, TimbreConfig, dump_config, parse_config
from timbre.errors import UnknownBackend
from timbre.manager import BackendManager
from timbre.models import download_model, model_records, set_active_model
from timbre.voices.store import VoiceStore

router = APIRouter()


class BackendAction(BaseModel):
    action: Literal["load", "unload", "enable", "disable"]


class ModelAction(BaseModel):
    action: Literal["download", "set_active"]


class VoiceAliasPayload(BaseModel):
    backend: str
    alias: str
    target: str


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
    return {"object": "list", "data": model_records(request.app.state.config)}


@router.post("/v1/models/{profile_id:path}")
async def control_model(profile_id: str, payload: ModelAction, request: Request) -> dict[str, object]:
    try:
        if payload.action == "download":
            path = await asyncio.to_thread(download_model, profile_id)
            return {
                "object": "list",
                "path": str(path),
                "data": model_records(request.app.state.config),
            }
        config = set_active_model(request.app.state.config, profile_id)
        await _replace_config(request, config)
        return {"object": "list", "data": model_records(config)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/v1/voices")
async def voices(request: Request) -> dict[str, object]:
    store = request.app.state.voice_store
    backend_voices = request.app.state.manager.all_voices()
    cloned = [
        {
            "name": record.name,
            "type": "cloned",
            "audio_path": str(record.audio_path) if record.audio_path else None,
            "prepared_backends": _prepared_backends(record.name, record.caches, backend_voices),
        }
        for record in store.list()
    ]
    cloned_names = {record["name"] for record in cloned}
    presets = [
        {"name": voice, "backend": backend, "type": "preset"}
        for backend, voices_for_backend in backend_voices.items()
        for voice in voices_for_backend
        if voice not in cloned_names
    ]
    aliases = [
        {"name": alias, "backend": backend, "target": target, "type": "alias"}
        for backend, backend_aliases in request.app.state.config.voices.aliases.items()
        for alias, target in backend_aliases.items()
    ]
    return {"object": "list", "data": aliases + presets + cloned}


def _backend_from_cache(filename: str) -> str:
    return filename.split(".", 1)[0]


def _prepared_backends(name: str, caches: list[Any], backend_voices: dict[str, list[str]]) -> list[str]:
    prepared = {_backend_from_cache(path.name) for path in caches}
    for backend, voices_for_backend in backend_voices.items():
        if name in voices_for_backend:
            prepared.add(backend)
    return sorted(prepared)


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

    await _replace_config(request, config)

    return {
        "path": str(getattr(request.app.state, "config_path", CONFIG_PATH)),
        "config": dump_config(config),
    }


@router.post("/v1/voices/aliases")
async def set_voice_alias(payload: VoiceAliasPayload, request: Request) -> dict[str, object]:
    backend = payload.backend.strip()
    alias = payload.alias.strip()
    target = payload.target.strip()
    if not backend or not alias or not target:
        raise HTTPException(status_code=400, detail="backend, alias, and target are required")
    if backend not in request.app.state.config.tts.backends:
        raise HTTPException(status_code=404, detail=f"Unknown TTS backend '{backend}'.")
    config = request.app.state.config
    config.voices.aliases.setdefault(backend, {})[alias] = target
    await _replace_config(request, config)
    return await voices(request)


@router.delete("/v1/voices/aliases/{backend}/{alias}")
async def delete_voice_alias(backend: str, alias: str, request: Request) -> dict[str, object]:
    config = request.app.state.config
    backend_aliases = config.voices.aliases.get(backend)
    if not backend_aliases or alias not in backend_aliases:
        raise HTTPException(status_code=404, detail=f"Unknown voice alias '{backend}/{alias}'.")
    del backend_aliases[alias]
    if not backend_aliases:
        del config.voices.aliases[backend]
    await _replace_config(request, config)
    return await voices(request)


@router.post("/v1/backends/{kind}/{name}")
async def control_backend(
    kind: Literal["tts", "stt"],
    name: str,
    payload: BackendAction,
    request: Request,
) -> dict[str, list[dict[str, object]]]:
    manager = request.app.state.manager
    try:
        if payload.action == "load":
            await manager.load_backend(kind, name)
        elif payload.action == "unload":
            await manager.unload_backend(kind, name)
        else:
            config = _config_with_backend_enabled(request.app.state.config, kind, name, payload.action == "enable")
            await _replace_config(request, config)
    except UnknownBackend as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return await backends(request)


async def _replace_config(request: Request, config: TimbreConfig) -> None:
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


def _config_with_backend_enabled(
    config: TimbreConfig, kind: Literal["tts", "stt"], name: str, enabled: bool
) -> TimbreConfig:
    group = _group_for_kind(config, kind)
    backend = group.backends.get(name)
    if backend is None:
        raise UnknownBackend(f"Unknown {kind.upper()} backend '{name}'.")
    backend.enabled = enabled
    if not enabled and group.default == name:
        replacement = next(
            (candidate for candidate, cfg in group.backends.items() if candidate != name and cfg.enabled),
            name,
        )
        group.default = replacement
    return config


def _group_for_kind(config: TimbreConfig, kind: Literal["tts", "stt"]) -> BackendGroupConfig:
    return config.tts if kind == "tts" else config.stt
