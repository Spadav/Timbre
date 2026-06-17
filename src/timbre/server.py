from __future__ import annotations

from contextlib import asynccontextmanager
import mimetypes
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse, Response

from timbre.api.discovery import router as discovery_router
from timbre.api.qwen import QWEN_VOICES_DIR, router as qwen_router
from timbre.api.speech import router as speech_router
from timbre.api.transcribe import router as transcribe_router
from timbre.api.voices import router as voices_router
from timbre.config import CONFIG_PATH, TimbreConfig, load_config
from timbre.eventlog import EventLog, configure_logging
from timbre.manager import BackendManager
from timbre.voices.store import VoiceStore


def create_app(config: TimbreConfig | None = None) -> FastAPI:
    configure_logging()
    cfg = config or load_config()
    manager = BackendManager(cfg)
    voice_store = VoiceStore(Path(cfg.voices.dir))
    qwen_voice_store = VoiceStore(QWEN_VOICES_DIR)
    event_log = EventLog()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        manager.start_sweeper()
        try:
            yield
        finally:
            await manager.stop_sweeper()

    app = FastAPI(title="Timbre", version="0.1.0", lifespan=lifespan)
    app.state.config = cfg
    app.state.config_path = CONFIG_PATH
    app.state.manager = manager
    app.state.voice_store = voice_store
    app.state.qwen_voice_store = qwen_voice_store
    app.state.event_log = event_log
    app.include_router(discovery_router)
    app.include_router(qwen_router)
    app.include_router(speech_router)
    app.include_router(transcribe_router)
    app.include_router(voices_router)
    _mount_ui(app)
    return app


def _mount_ui(app: FastAPI) -> None:
    project_root = Path(__file__).resolve().parents[2]
    ui_dist = _ui_dist_path(project_root)
    if ui_dist.exists():
        ui_root = ui_dist.resolve()

        @app.get("/ui", include_in_schema=False)
        async def ui_redirect() -> RedirectResponse:
            return RedirectResponse("/ui/")

        @app.get("/ui/", include_in_schema=False)
        async def ui_index() -> Response:
            return _ui_file_response(ui_root, "index.html")

        @app.get("/ui/{asset_path:path}", include_in_schema=False)
        async def ui_asset(asset_path: str) -> Response:
            return _ui_file_response(ui_root, asset_path)


def _ui_dist_path(project_root: Path) -> Path:
    source_dist = project_root / "web" / "dist"
    if source_dist.exists():
        return source_dist
    return Path(__file__).resolve().parent / "web" / "dist"


def _ui_file_response(root: Path, asset_path: str) -> Response:
    path = (root / asset_path).resolve()
    if root not in path.parents and path != root:
        raise HTTPException(status_code=404)
    if not path.is_file():
        if "." not in Path(asset_path).name:
            path = root / "index.html"
        else:
            raise HTTPException(status_code=404)

    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return Response(path.read_bytes(), media_type=media_type)
