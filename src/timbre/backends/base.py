from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any


class BaseBackend(ABC):
    name: str

    def __init__(self, config: dict[str, Any], voices_dir: str | None = None) -> None:
        self.config = config
        self.voices_dir = voices_dir
        self._loaded = False
        self.last_used = 0.0

    async def ensure_loaded(self) -> None:
        if not self._loaded:
            await self._load()
            self._loaded = True
        self.touch()

    def touch(self) -> None:
        self.last_used = time.monotonic()

    async def maybe_unload(self, ttl: int) -> bool:
        if ttl == 0 or not self._loaded:
            return False
        if time.monotonic() - self.last_used < ttl:
            return False
        await self.unload()
        return True

    async def unload(self) -> None:
        await self._unload()
        self._loaded = False

    @abstractmethod
    async def _load(self) -> None:
        raise NotImplementedError

    async def _unload(self) -> None:
        return None

    @property
    def loaded(self) -> bool:
        return self._loaded


class TTSBackend(BaseBackend):
    @abstractmethod
    async def synthesize(self, text: str, voice: str, **opts: Any) -> bytes:
        raise NotImplementedError

    @property
    def voices(self) -> list[str]:
        return []


class STTBackend(BaseBackend):
    @abstractmethod
    async def transcribe(self, audio: bytes, **opts: Any) -> str:
        raise NotImplementedError
