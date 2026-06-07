from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from timbre.api.discovery import router as discovery_router
from timbre.api.speech import router as speech_router
from timbre.api.transcribe import router as transcribe_router
from timbre.api.voices import router as voices_router
from timbre.config import TimbreConfig, load_config
from timbre.manager import BackendManager
from timbre.voices.store import VoiceStore


def create_app(config: TimbreConfig | None = None) -> FastAPI:
    cfg = config or load_config()
    manager = BackendManager(cfg)
    voice_store = VoiceStore(Path(cfg.voices.dir))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.config = cfg
        app.state.manager = manager
        app.state.voice_store = voice_store
        manager.start_sweeper()
        try:
            yield
        finally:
            await manager.stop_sweeper()

    app = FastAPI(title="Timbre", version="0.1.0", lifespan=lifespan)
    app.include_router(discovery_router)
    app.include_router(speech_router)
    app.include_router(transcribe_router)
    app.include_router(voices_router)
    _mount_ui(app)
    return app


def _mount_ui(app: FastAPI) -> None:
    project_root = Path(__file__).resolve().parents[2]
    ui_dist = project_root / "web" / "dist"
    if ui_dist.exists():
        app.mount("/ui", StaticFiles(directory=ui_dist, html=True), name="ui")
