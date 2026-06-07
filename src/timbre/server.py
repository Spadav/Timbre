from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI

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
    _mount_gradio(app)
    return app


def _mount_gradio(app: FastAPI) -> None:
    try:
        import gradio as gr
    except ImportError:
        return

    with gr.Blocks(title="Timbre") as demo:
        gr.Markdown("# Timbre")
        with gr.Tab("Speech"):
            text = gr.Textbox(label="Text")
            model = gr.Textbox(label="TTS model", value="pocket")
            voice = gr.Textbox(label="Voice", value="default")
            output = gr.Audio(label="Audio", type="filepath")
            gr.Button("Generate").click(
                _ui_speech_placeholder, inputs=[text, model, voice], outputs=[output]
            )
        with gr.Tab("Status"):
            gr.JSON(label="Backends")

    gr.mount_gradio_app(app, demo, path="/ui")


def _ui_speech_placeholder(text: str, model: str, voice: str) -> None:
    return None
