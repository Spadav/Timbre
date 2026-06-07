from __future__ import annotations

from typing import Any

import pytest

from timbre.backends.base import TTSBackend
from timbre.config import default_config
from timbre.manager import BackendManager


class FakeTTS(TTSBackend):
    name = "fake"

    async def _load(self) -> None:
        self.config["loads"] = self.config.get("loads", 0) + 1

    async def synthesize(self, text: str, voice: str, **opts: Any) -> bytes:
        await self.ensure_loaded()
        return b"RIFF....WAVE"


@pytest.mark.asyncio
async def test_manager_loads_once_and_unloads_by_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    import timbre.manager as manager_module

    monkeypatch.setitem(manager_module.TTS_BACKENDS, "fake", FakeTTS)
    config = default_config()
    config.tts.default = "fake"
    config.tts.backends = {"fake": config.tts.backends["pocket"]}
    config.tts.backends["fake"].ttl = 1
    manager = BackendManager(config)

    backend = await manager.get_tts("fake")
    assert backend.loaded
    assert backend.config["loads"] == 1

    backend.last_used -= 10
    await manager.sweep_once()
    assert not backend.loaded
