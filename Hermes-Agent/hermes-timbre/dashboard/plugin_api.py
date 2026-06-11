"""Dashboard API for the hermes-timbre plugin.

Mounted by Hermes at /api/plugins/hermes-timbre/.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel
except Exception:  # pragma: no cover - lets local syntax checks run without FastAPI.
    class HTTPException(Exception):  # type: ignore[no-redef]
        def __init__(self, status_code: int, detail: str):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class APIRouter:  # type: ignore[no-redef]
        def get(self, *_args, **_kwargs):
            return lambda fn: fn

        def post(self, *_args, **_kwargs):
            return lambda fn: fn

    class BaseModel:  # type: ignore[no-redef]
        pass


CONFIG_PATH = Path.home() / ".hermes" / "hermes-timbre.json"
router = APIRouter()


class ConfigUpdate(BaseModel):
    url: str | None = None
    tts_backend: str | None = None
    stt_backend: str | None = None
    voice: str | None = None


def _load_config() -> dict[str, str]:
    data: dict[str, Any] = {}
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
    url = os.environ.get("TIMBRE_URL") or str(data.get("url") or "")
    return {
        "url": url.rstrip("/"),
        "tts_backend": os.environ.get("TIMBRE_TTS_BACKEND")
        or str(data.get("tts_backend") or "pocket"),
        "stt_backend": os.environ.get("TIMBRE_STT_BACKEND")
        or str(data.get("stt_backend") or "parakeet"),
        "voice": os.environ.get("TIMBRE_TTS_VOICE") or str(data.get("voice") or "alba"),
    }


def _save_config(config: dict[str, str]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _endpoint(path: str) -> str:
    config = _load_config()
    if not config["url"]:
        raise HTTPException(
            status_code=400,
            detail="Timbre is not configured. Run `hermes timbre setup` first.",
        )
    return config["url"] + path


def _request_json(path: str, *, timeout: float = 10.0) -> dict[str, Any]:
    request = urllib.request.Request(_endpoint(path), headers={"accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") or exc.reason
        raise HTTPException(status_code=exc.code, detail=detail) from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail=str(exc.reason)) from exc
    return json.loads(payload.decode("utf-8") or "{}")


def _post_json(path: str, payload: dict[str, Any], *, timeout: float = 20.0) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        _endpoint(path),
        data=body,
        headers={"content-type": "application/json", "accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") or exc.reason
        raise HTTPException(status_code=exc.code, detail=detail) from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail=str(exc.reason)) from exc
    return json.loads(raw.decode("utf-8") or "{}")


@router.get("/summary")
async def summary() -> dict[str, Any]:
    config = _load_config()
    result: dict[str, Any] = {"config": config, "configured": bool(config["url"])}
    if not config["url"]:
        return result

    health_error = None
    backends_error = None
    voices_error = None
    try:
        result["health"] = _request_json("/health", timeout=5.0)
    except HTTPException as exc:
        health_error = exc.detail
        result["health"] = None
    try:
        result["backends"] = _request_json("/v1/backends", timeout=10.0).get("data", [])
    except HTTPException as exc:
        backends_error = exc.detail
        result["backends"] = []
    try:
        result["voices"] = _request_json("/v1/voices", timeout=10.0).get("data", [])
    except HTTPException as exc:
        voices_error = exc.detail
        result["voices"] = []

    result["errors"] = {
        "health": health_error,
        "backends": backends_error,
        "voices": voices_error,
    }
    return result


@router.post("/backends/{kind}/{name}/{action}")
async def backend_action(kind: str, name: str, action: str) -> dict[str, Any]:
    if kind not in {"tts", "stt"}:
        raise HTTPException(status_code=400, detail="kind must be tts or stt")
    if action not in {"load", "unload", "enable", "disable"}:
        raise HTTPException(status_code=400, detail="invalid backend action")
    return _post_json(f"/v1/backends/{kind}/{name}", {"action": action}, timeout=30.0)


@router.post("/config")
async def update_config(payload: ConfigUpdate) -> dict[str, Any]:
    config = _load_config()
    for key in ("url", "tts_backend", "stt_backend", "voice"):
        value = getattr(payload, key, None)
        if value is not None:
            config[key] = str(value).strip().rstrip("/") if key == "url" else str(value).strip()

    backends: list[dict[str, Any]] = []
    voices: list[dict[str, Any]] = []
    if config["url"]:
        original = _load_config()
        try:
            _save_config(config)
            backends = _request_json("/v1/backends", timeout=10.0).get("data", [])
            voices = _request_json("/v1/voices", timeout=10.0).get("data", [])
        finally:
            _save_config(original)

    tts_names = [
        str(item.get("name"))
        for item in backends
        if item.get("kind") == "tts" and item.get("enabled", True)
    ]
    stt_names = [
        str(item.get("name"))
        for item in backends
        if item.get("kind") == "stt" and item.get("enabled", True)
    ]
    if tts_names and config["tts_backend"] not in tts_names:
        raise HTTPException(status_code=400, detail=f"Unknown TTS backend: {config['tts_backend']}")
    if stt_names and config["stt_backend"] not in stt_names:
        raise HTTPException(status_code=400, detail=f"Unknown STT backend: {config['stt_backend']}")

    voice_names = {
        str(item.get("name"))
        for item in voices
        if str(item.get("name") or "").strip()
        and (not item.get("backend") or item.get("backend") == config["tts_backend"])
    }
    if voice_names and config["voice"] not in voice_names:
        # Custom cloned voice names are allowed because Timbre may accept voices
        # not returned by /v1/voices yet.
        pass

    _save_config(config)
    return await summary()
