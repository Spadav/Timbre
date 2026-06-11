"""Hermes Agent plugin for Timbre voice gateway."""

from __future__ import annotations

import json
import mimetypes
import os
import shlex
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

try:
    from agent.tts_provider import TTSProvider
except Exception:  # pragma: no cover - Hermes is optional during local linting.
    class TTSProvider:  # type: ignore[no-redef]
        pass

try:
    from agent.transcription_provider import TranscriptionProvider
except Exception:  # pragma: no cover - Hermes is optional during local linting.
    class TranscriptionProvider:  # type: ignore[no-redef]
        pass


PLUGIN_NAME = "hermes-timbre"
PROVIDER_NAME = "timbre"
DEFAULT_URL = ""
DEFAULT_TTS_BACKEND = "pocket"
DEFAULT_STT_BACKEND = "parakeet"
DEFAULT_TTS_VOICE = "alba"
CONFIG_PATH = Path.home() / ".hermes" / "hermes-timbre.json"
HERMES_CONFIG_PATH = Path.home() / ".hermes" / "config.yaml"


class TimbreConfig:
    def __init__(
        self,
        *,
        url: str = DEFAULT_URL,
        tts_backend: str = DEFAULT_TTS_BACKEND,
        stt_backend: str = DEFAULT_STT_BACKEND,
        voice: str = DEFAULT_TTS_VOICE,
    ) -> None:
        self.url = normalize_url(url)
        self.tts_backend = tts_backend or DEFAULT_TTS_BACKEND
        self.stt_backend = stt_backend or DEFAULT_STT_BACKEND
        self.voice = voice or DEFAULT_TTS_VOICE

    @classmethod
    def load(cls) -> "TimbreConfig":
        data: dict[str, Any] = {}
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}

        return cls(
            url=os.environ.get("TIMBRE_URL") or str(data.get("url") or DEFAULT_URL),
            tts_backend=os.environ.get("TIMBRE_TTS_BACKEND")
            or str(data.get("tts_backend") or DEFAULT_TTS_BACKEND),
            stt_backend=os.environ.get("TIMBRE_STT_BACKEND")
            or str(data.get("stt_backend") or DEFAULT_STT_BACKEND),
            voice=os.environ.get("TIMBRE_TTS_VOICE") or str(data.get("voice") or DEFAULT_TTS_VOICE),
        )

    def save(self) -> None:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps(
                {
                    "url": self.url,
                    "tts_backend": self.tts_backend,
                    "stt_backend": self.stt_backend,
                    "voice": self.voice,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    return url.rstrip("/")


def _endpoint(path: str, config: TimbreConfig | None = None) -> str:
    config = config or TimbreConfig.load()
    if not config.url:
        raise RuntimeError("Timbre is not configured. Run /timbre <url> to connect.")
    return config.url + path


def _request_json(url: str, *, timeout: float = 5.0) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read()
    return json.loads(payload.decode("utf-8") or "{}")


def _post_json(url: str, payload: dict[str, Any], *, timeout: float) -> bytes:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "content-type": "application/json",
            "accept": "*/*",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _post_multipart(
    url: str,
    *,
    fields: dict[str, str],
    file_field: str,
    file_path: str | os.PathLike[str],
    timeout: float,
) -> dict[str, Any]:
    boundary = "----hermes-timbre-" + uuid.uuid4().hex
    path = Path(file_path)
    filename = path.name or "audio.wav"
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    body_parts: list[bytes] = []

    for name, value in fields.items():
        if value is None:
            continue
        body_parts.append(f"--{boundary}\r\n".encode("utf-8"))
        body_parts.append(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8")
        )

    body_parts.append(f"--{boundary}\r\n".encode("utf-8"))
    body_parts.append(
        (
            f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
    )
    body_parts.append(path.read_bytes())
    body_parts.append(b"\r\n")
    body_parts.append(f"--{boundary}--\r\n".encode("utf-8"))

    request = urllib.request.Request(
        url,
        data=b"".join(body_parts),
        headers={
            "content-type": f"multipart/form-data; boundary={boundary}",
            "accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read()
    return json.loads(payload.decode("utf-8") or "{}")


def _http_error_message(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            detail = ""
        return f"HTTP {exc.code}: {detail or exc.reason}"
    if isinstance(exc, urllib.error.URLError):
        return str(exc.reason)
    return str(exc)


def _backends(config: TimbreConfig | None = None) -> list[dict[str, Any]]:
    payload = _request_json(_endpoint("/v1/backends", config), timeout=5.0)
    data = payload.get("data", [])
    return data if isinstance(data, list) else []


def _voices(config: TimbreConfig | None = None) -> list[dict[str, Any]]:
    payload = _request_json(_endpoint("/v1/voices", config), timeout=5.0)
    data = payload.get("data", [])
    return data if isinstance(data, list) else []


def _filter_backend_names(backends: list[dict[str, Any]], kind: str) -> list[str]:
    return [
        str(item.get("name"))
        for item in backends
        if item.get("kind") == kind and item.get("enabled", True)
    ]


class TimbreTTSProvider(TTSProvider):
    @property
    def name(self) -> str:
        return PROVIDER_NAME

    @property
    def display_name(self) -> str:
        return "Timbre"

    @property
    def voice_compatible(self) -> bool:
        return True

    def is_available(self) -> bool:
        return bool(TimbreConfig.load().url)

    def default_model(self) -> str:
        return TimbreConfig.load().tts_backend

    def list_models(self) -> list[dict[str, Any]]:
        try:
            return [
                {"id": name, "display": name, "languages": [], "max_text_length": 5000}
                for name in _filter_backend_names(_backends(), "tts")
            ]
        except Exception:
            return []

    def list_voices(self) -> list[dict[str, Any]]:
        try:
            voices = []
            for voice in _voices():
                if voice.get("backend") and voice.get("backend") != TimbreConfig.load().tts_backend:
                    continue
                name = str(voice.get("name") or "")
                if name:
                    voices.append({"id": name, "display": name, "language": "", "gender": ""})
            return voices
        except Exception:
            return []

    def get_setup_schema(self) -> dict[str, Any]:
        return {
            "name": "Timbre",
            "badge": "local",
            "tag": "Local TTS/STT gateway",
            "env_vars": [{"key": "TIMBRE_URL", "prompt": "Timbre server URL"}],
        }

    def synthesize(
        self,
        text: str,
        output_path: str,
        *,
        voice: str | None = None,
        model: str | None = None,
        speed: float | None = None,
        format: str = "mp3",
        **extra: Any,
    ) -> str:
        del extra
        config = TimbreConfig.load()
        payload: dict[str, Any] = {
            "model": model or config.tts_backend,
            "input": text,
            "voice": voice or config.voice,
            "response_format": format or "mp3",
        }
        if speed is not None:
            payload["speed"] = speed
        try:
            audio = _post_json(_endpoint("/v1/audio/speech", config), payload, timeout=30.0)
        except Exception as exc:
            raise RuntimeError(f"Timbre TTS failed: {_http_error_message(exc)}") from exc
        Path(output_path).write_bytes(audio)
        return output_path


class TimbreTranscriptionProvider(TranscriptionProvider):
    @property
    def name(self) -> str:
        return PROVIDER_NAME

    @property
    def display_name(self) -> str:
        return "Timbre"

    def is_available(self) -> bool:
        return bool(TimbreConfig.load().url)

    def default_model(self) -> str:
        return TimbreConfig.load().stt_backend

    def list_models(self) -> list[dict[str, Any]]:
        try:
            return [
                {"id": name, "display": name, "languages": [], "max_audio_seconds": None}
                for name in _filter_backend_names(_backends(), "stt")
            ]
        except Exception:
            return []

    def get_setup_schema(self) -> dict[str, Any]:
        return {
            "name": "Timbre",
            "badge": "local",
            "tag": "Local STT gateway",
            "env_vars": [{"key": "TIMBRE_URL", "prompt": "Timbre server URL"}],
        }

    def transcribe(
        self,
        file_path: str,
        *,
        model: str | None = None,
        language: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        del extra
        config = TimbreConfig.load()
        fields = {"model": model or config.stt_backend}
        if language:
            fields["language"] = language
        try:
            payload = _post_multipart(
                _endpoint("/v1/audio/transcriptions", config),
                fields=fields,
                file_field="file",
                file_path=file_path,
                timeout=10.0,
            )
            text = str(payload.get("text") or payload.get("transcript") or "")
            return {"success": True, "transcript": text, "provider": PROVIDER_NAME}
        except Exception as exc:
            return {
                "success": False,
                "transcript": "",
                "error": f"Timbre STT failed: {_http_error_message(exc)}",
                "provider": PROVIDER_NAME,
            }


def parse_command_args(raw: Any) -> tuple[str, dict[str, str]]:
    if isinstance(raw, dict):
        tokens = [str(raw.get("url") or raw.get("arg") or raw.get("args") or "").strip()]
        options = {
            "tts": str(raw.get("tts") or raw.get("tts_backend") or "").strip(),
            "stt": str(raw.get("stt") or raw.get("stt_backend") or "").strip(),
            "voice": str(raw.get("voice") or "").strip(),
        }
        return tokens[0], {key: value for key, value in options.items() if value}

    text = str(raw or "").strip()
    if not text:
        return "", {}
    parts = shlex.split(text)
    command = parts[0] if parts else ""
    options: dict[str, str] = {}
    index = 1
    while index < len(parts):
        token = parts[index]
        if token in {"--tts", "--stt", "--voice"} and index + 1 < len(parts):
            options[token.removeprefix("--")] = parts[index + 1]
            index += 2
        else:
            index += 1
    return command, options


def handle_timbre_command(raw: Any = "", **kwargs: Any) -> str:
    if not raw and kwargs:
        raw = kwargs.get("args") or kwargs.get("text") or kwargs

    command, options = parse_command_args(raw)
    config = TimbreConfig.load()

    if not command:
        return "Usage: /timbre <url> [--tts pocket] [--stt parakeet] [--voice alba]"

    if command == "status":
        return timbre_status(config)

    if command == "backends":
        return timbre_backends(config)

    config = TimbreConfig(
        url=command,
        tts_backend=options.get("tts") or config.tts_backend,
        stt_backend=options.get("stt") or config.stt_backend,
        voice=options.get("voice") or config.voice,
    )

    try:
        _request_json(_endpoint("/health", config), timeout=5.0)
        backends = _backends(config)
    except Exception as exc:
        return f"Could not connect to Timbre at {config.url}: {_http_error_message(exc)}"

    config.save()
    config_result = set_hermes_voice_providers()
    tts_names = ", ".join(_filter_backend_names(backends, "tts")) or "none"
    stt_names = ", ".join(_filter_backend_names(backends, "stt")) or "none"
    return (
        f"Connected to Timbre at {config.url}. "
        f"Available TTS: {tts_names}. Available STT: {stt_names}. "
        f"Default TTS backend: {config.tts_backend}. "
        f"Default STT backend: {config.stt_backend}. "
        f"{config_result}"
    )


def timbre_status(config: TimbreConfig | None = None) -> str:
    config = config or TimbreConfig.load()
    if not config.url:
        return "Timbre is not configured. Run /timbre <url> to connect."
    try:
        health = _request_json(_endpoint("/health", config), timeout=5.0)
        status = health.get("status", "unknown")
        reachable = f"reachable ({status})"
    except Exception as exc:
        reachable = f"unreachable ({_http_error_message(exc)})"
    return (
        f"Timbre URL: {config.url}\n"
        f"Status: {reachable}\n"
        f"TTS backend: {config.tts_backend}\n"
        f"STT backend: {config.stt_backend}\n"
        f"TTS voice: {config.voice}"
    )


def timbre_backends(config: TimbreConfig | None = None) -> str:
    config = config or TimbreConfig.load()
    try:
        rows = _backends(config)
    except Exception as exc:
        return f"Could not fetch Timbre backends: {_http_error_message(exc)}"
    if not rows:
        return "Timbre returned no backends."
    lines = ["Timbre backends:"]
    for item in rows:
        name = item.get("name", "?")
        kind = item.get("kind", "?")
        enabled = "enabled" if item.get("enabled") else "disabled"
        loaded = "loaded" if item.get("loaded") else "unloaded"
        device = item.get("device") or "default"
        lines.append(f"- {kind}/{name}: {enabled}, {loaded}, device={device}")
    return "\n".join(lines)


def set_hermes_voice_providers() -> str:
    try:
        import yaml  # type: ignore[import-untyped]
    except Exception:
        return "Saved plugin config. Install PyYAML in Hermes to auto-update config.yaml."

    try:
        HERMES_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        if HERMES_CONFIG_PATH.exists():
            data = yaml.safe_load(HERMES_CONFIG_PATH.read_text(encoding="utf-8")) or {}
        else:
            data = {}
        if not isinstance(data, dict):
            data = {}
        tts = data.setdefault("tts", {})
        stt = data.setdefault("stt", {})
        if isinstance(tts, dict):
            tts["provider"] = PROVIDER_NAME
        if isinstance(stt, dict):
            stt["provider"] = PROVIDER_NAME
        HERMES_CONFIG_PATH.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        return "Set Hermes TTS and STT providers to timbre."
    except Exception as exc:
        return f"Saved plugin config, but could not update Hermes config.yaml: {exc}"


def register_cli(parser: Any) -> None:
    subcommands = parser.add_subparsers(dest="timbre_command")

    setup = subcommands.add_parser("setup", help="Connect Hermes to a Timbre server")
    setup.add_argument("url")
    setup.add_argument("--tts", default="")
    setup.add_argument("--stt", default="")
    setup.add_argument("--voice", default="")

    subcommands.add_parser("status", help="Show Timbre connection status")
    subcommands.add_parser("backends", help="List Timbre backends")


def handle_cli(args: Any) -> str:
    command = getattr(args, "timbre_command", None)
    if command == "setup":
        raw = getattr(args, "url", "")
        if getattr(args, "tts", ""):
            raw += f" --tts {shlex.quote(args.tts)}"
        if getattr(args, "stt", ""):
            raw += f" --stt {shlex.quote(args.stt)}"
        if getattr(args, "voice", ""):
            raw += f" --voice {shlex.quote(args.voice)}"
        return handle_timbre_command(raw)
    if command == "backends":
        return timbre_backends()
    return timbre_status()


def register(ctx: Any) -> None:
    ctx.register_tts_provider(TimbreTTSProvider())
    ctx.register_transcription_provider(TimbreTranscriptionProvider())
    ctx.register_command("timbre", handle_timbre_command, "Configure and inspect Timbre voice gateway")

    if hasattr(ctx, "register_cli_command"):
        try:
            ctx.register_cli_command("timbre", "Configure Timbre voice gateway", register_cli, handle_cli)
        except TypeError:
            pass

    if not TimbreConfig.load().url:
        print("Timbre not configured. Run /timbre <url> to connect.")
