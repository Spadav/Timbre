from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import logging
import time
from typing import Any
from uuid import uuid4


LOGGER = logging.getLogger("timbre")


@dataclass(slots=True)
class LogEvent:
    id: str
    ts: str
    level: str
    kind: str
    operation: str
    status: str
    message: str
    backend: str | None = None
    voice: str | None = None
    model: str | None = None
    format: str | None = None
    input_chars: int | None = None
    output_bytes: int | None = None
    duration: float | None = None
    client: str | None = None


class EventLog:
    def __init__(self, limit: int = 500) -> None:
        self._events: deque[LogEvent] = deque(maxlen=limit)

    def add(
        self,
        *,
        level: str = "info",
        kind: str = "system",
        operation: str,
        status: str,
        message: str,
        backend: str | None = None,
        voice: str | None = None,
        model: str | None = None,
        format: str | None = None,
        input_chars: int | None = None,
        output_bytes: int | None = None,
        duration: float | None = None,
        client: str | None = None,
    ) -> LogEvent:
        event = LogEvent(
            id=uuid4().hex,
            ts=datetime.now(timezone.utc).isoformat(),
            level=level,
            kind=kind,
            operation=operation,
            status=status,
            message=message,
            backend=backend,
            voice=voice,
            model=model,
            format=format,
            input_chars=input_chars,
            output_bytes=output_bytes,
            duration=duration,
            client=client,
        )
        self._events.appendleft(event)
        _emit(event)
        return event

    def list(self, limit: int = 200) -> list[dict[str, Any]]:
        return [asdict(event) for event in list(self._events)[:limit]]


class Timer:
    def __init__(self) -> None:
        self._start = time.perf_counter()

    @property
    def seconds(self) -> float:
        return time.perf_counter() - self._start


def configure_logging() -> None:
    if not LOGGER.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(message)s"))
        LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False


def event_log(request: Any) -> EventLog:
    log = getattr(request.app.state, "event_log", None)
    if log is None:
        log = EventLog()
        request.app.state.event_log = log
    return log


def client_host(request: Any) -> str | None:
    client = getattr(request, "client", None)
    return getattr(client, "host", None)


def _emit(event: LogEvent) -> None:
    details = [
        f"{event.kind}.{event.operation}",
        event.status,
        event.message,
    ]
    if event.backend:
        details.append(f"backend={event.backend}")
    if event.voice:
        details.append(f"voice={event.voice}")
    if event.model:
        details.append(f"model={event.model}")
    if event.duration is not None:
        details.append(f"duration={event.duration:.2f}s")
    if event.input_chars is not None:
        details.append(f"chars={event.input_chars}")
    if event.output_bytes is not None:
        details.append(f"bytes={event.output_bytes}")
    if event.client:
        details.append(f"client={event.client}")
    getattr(LOGGER, event.level.lower(), LOGGER.info)(" | ".join(details))
