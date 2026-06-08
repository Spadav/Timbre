from __future__ import annotations

import asyncio
import gc
from dataclasses import dataclass
from typing import Any

from timbre.backends.base import STTBackend, TTSBackend
from timbre.backends.registry import STT_BACKENDS, TTS_BACKENDS
from timbre.config import TimbreConfig
from timbre.errors import UnknownBackend


@dataclass(slots=True)
class BackendState:
    name: str
    kind: str
    enabled: bool
    loaded: bool
    ttl: int
    device: str


class BackendManager:
    def __init__(self, config: TimbreConfig) -> None:
        self.config = config
        self.tts: dict[str, TTSBackend] = {}
        self.stt: dict[str, STTBackend] = {}
        self._tts_ttls: dict[str, int] = {}
        self._stt_ttls: dict[str, int] = {}
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._sweep_task: asyncio.Task[None] | None = None
        self._build_backends()

    def _build_backends(self) -> None:
        voices_dir = str(self.config.voices.dir)
        for name, backend_config in self.config.tts.backends.items():
            if not backend_config.enabled or name not in TTS_BACKENDS:
                continue
            self.tts[name] = TTS_BACKENDS[name](backend_config.as_dict(), voices_dir=voices_dir)
            self._tts_ttls[name] = backend_config.ttl
            self._locks[("tts", name)] = asyncio.Lock()
        for name, backend_config in self.config.stt.backends.items():
            if not backend_config.enabled or name not in STT_BACKENDS:
                continue
            self.stt[name] = STT_BACKENDS[name](backend_config.as_dict(), voices_dir=voices_dir)
            self._stt_ttls[name] = backend_config.ttl
            self._locks[("stt", name)] = asyncio.Lock()

    async def get_tts(self, name: str | None) -> TTSBackend:
        resolved = name or self.config.tts.default
        backend = self.tts.get(resolved)
        if backend is None:
            raise UnknownBackend(f"Unknown TTS backend '{resolved}'. Available: {sorted(self.tts)}")
        async with self._locks[("tts", resolved)]:
            await backend.ensure_loaded()
        return backend

    async def get_stt(self, name: str | None) -> STTBackend:
        resolved = name or self.config.stt.default
        backend = self.stt.get(resolved)
        if backend is None:
            raise UnknownBackend(f"Unknown STT backend '{resolved}'. Available: {sorted(self.stt)}")
        async with self._locks[("stt", resolved)]:
            await backend.ensure_loaded()
        return backend

    def list_states(self) -> list[BackendState]:
        states: list[BackendState] = []
        for name, backend in self.tts.items():
            states.append(
                BackendState(name, "tts", True, backend.loaded, self._tts_ttls[name], backend.config["device"])
            )
        for name, backend in self.stt.items():
            states.append(
                BackendState(name, "stt", True, backend.loaded, self._stt_ttls[name], backend.config["device"])
            )
        return states

    def model_records(self) -> list[dict[str, Any]]:
        return [
            {"id": state.name, "object": "model", "owned_by": "timbre", "kind": state.kind}
            for state in self.list_states()
        ]

    def all_voices(self) -> dict[str, list[str]]:
        return {name: backend.voices for name, backend in self.tts.items()}

    async def prepare_voice_clone(
        self, voice: str, backend_name: str | None = None
    ) -> list[dict[str, str]]:
        results: list[dict[str, str]] = []
        names = [backend_name] if backend_name else list(self.tts)
        for name in names:
            backend = self.tts.get(name)
            if backend is None:
                raise UnknownBackend(f"Unknown TTS backend '{name}'. Available: {sorted(self.tts)}")
            prepare = getattr(backend, "prepare_voice_clone", None)
            if not callable(prepare):
                continue
            async with self._locks[("tts", name)]:
                results.append(await prepare(voice))
        return results

    async def sweep_once(self) -> None:
        for name, backend in self.tts.items():
            if await backend.maybe_unload(self._tts_ttls[name]):
                self._after_unload()
        for name, backend in self.stt.items():
            if await backend.maybe_unload(self._stt_ttls[name]):
                self._after_unload()

    def start_sweeper(self) -> None:
        if not self.tts and not self.stt:
            return
        if self._sweep_task is None or self._sweep_task.done():
            self._sweep_task = asyncio.create_task(self._sweep_loop())

    async def stop_sweeper(self) -> None:
        if self._sweep_task is None:
            return
        self._sweep_task.cancel()
        try:
            await self._sweep_task
        except asyncio.CancelledError:
            pass
        self._sweep_task = None

    async def _sweep_loop(self) -> None:
        interval = max(1, self.config.server.ttl_check_interval)
        while True:
            await asyncio.sleep(interval)
            await self.sweep_once()

    @staticmethod
    def _after_unload() -> None:
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
