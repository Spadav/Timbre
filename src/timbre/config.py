from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

APP_NAME = "timbre"
CONFIG_DIR = Path.home() / ".config" / APP_NAME
CONFIG_PATH = CONFIG_DIR / "config.yaml"


@dataclass(slots=True)
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 9000
    ttl_check_interval: int = 30


@dataclass(slots=True)
class BackendConfig:
    enabled: bool = True
    device: str = "cpu"
    ttl: int = 300
    options: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "device": self.device, "ttl": self.ttl, **self.options}


@dataclass(slots=True)
class BackendGroupConfig:
    default: str
    backends: dict[str, BackendConfig]


@dataclass(slots=True)
class VoicesConfig:
    dir: Path = CONFIG_DIR / "voices"


@dataclass(slots=True)
class TimbreConfig:
    server: ServerConfig
    tts: BackendGroupConfig
    stt: BackendGroupConfig
    voices: VoicesConfig


def _expand_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def default_config() -> TimbreConfig:
    return TimbreConfig(
        server=ServerConfig(),
        tts=BackendGroupConfig(
            default="pocket",
            backends={
                "pocket": BackendConfig(enabled=True, device="cpu", ttl=0),
                "supertonic": BackendConfig(
                    enabled=True,
                    device="cpu",
                    ttl=300,
                    options={
                        "model": "supertonic-3",
                        "model_path": str(CONFIG_DIR / "models" / "supertonic" / "supertonic-3"),
                        "steps": 8,
                    },
                ),
            },
        ),
        stt=BackendGroupConfig(
            default="whisper",
            backends={
                "whisper": BackendConfig(
                    enabled=True,
                    device="cpu",
                    ttl=300,
                    options={
                        "model_size": "base",
                        "model_path": str(CONFIG_DIR / "models" / "whisper" / "base"),
                    },
                ),
                "parakeet": BackendConfig(
                    enabled=True,
                    device="cpu",
                    ttl=300,
                    options={
                        "model": "parakeet-tdt-0.6b-v3",
                        "repo_id": "nemo-parakeet-tdt-0.6b-v3",
                        "quantization": "int8",
                        "model_path": str(CONFIG_DIR / "models" / "parakeet" / "int8"),
                    },
                ),
            },
        ),
        voices=VoicesConfig(),
    )


def load_config(path: str | Path | None = None) -> TimbreConfig:
    cfg = default_config()
    config_path = _expand_path(path or CONFIG_PATH)
    if not config_path.exists():
        return cfg
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return parse_config(raw)


def parse_config(raw: dict[str, Any]) -> TimbreConfig:
    defaults = default_config()
    server_raw = raw.get("server", {}) or {}
    voices_raw = raw.get("voices", {}) or {}
    return TimbreConfig(
        server=ServerConfig(
            host=str(server_raw.get("host", defaults.server.host)),
            port=int(server_raw.get("port", defaults.server.port)),
            ttl_check_interval=int(
                server_raw.get("ttl_check_interval", defaults.server.ttl_check_interval)
            ),
        ),
        tts=_parse_group(raw.get("tts", {}) or {}, defaults.tts),
        stt=_parse_group(raw.get("stt", {}) or {}, defaults.stt),
        voices=VoicesConfig(dir=_expand_path(voices_raw.get("dir", defaults.voices.dir))),
    )


def _parse_group(raw: dict[str, Any], defaults: BackendGroupConfig) -> BackendGroupConfig:
    backends = dict(defaults.backends)
    for name, backend_raw in (raw.get("backends", {}) or {}).items():
        backend_raw = backend_raw or {}
        known = backends.get(name, BackendConfig())
        options = {
            key: value
            for key, value in backend_raw.items()
            if key not in {"enabled", "device", "ttl"}
        }
        merged_options = {**known.options, **options}
        backends[name] = BackendConfig(
            enabled=bool(backend_raw.get("enabled", known.enabled)),
            device=str(backend_raw.get("device", known.device)),
            ttl=int(backend_raw.get("ttl", known.ttl)),
            options=merged_options,
        )
    return BackendGroupConfig(default=str(raw.get("default", defaults.default)), backends=backends)


def dump_config(config: TimbreConfig) -> dict[str, Any]:
    return {
        "server": {
            "host": config.server.host,
            "port": config.server.port,
            "ttl_check_interval": config.server.ttl_check_interval,
        },
        "tts": _dump_group(config.tts),
        "stt": _dump_group(config.stt),
        "voices": {"dir": str(config.voices.dir)},
    }


def _dump_group(group: BackendGroupConfig) -> dict[str, Any]:
    return {
        "default": group.default,
        "backends": {name: backend.as_dict() for name, backend in group.backends.items()},
    }


def write_default_config(path: str | Path | None = None, overwrite: bool = False) -> Path:
    config_path = _expand_path(path or CONFIG_PATH)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists() and not overwrite:
        return config_path
    with config_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(dump_config(default_config()), handle, sort_keys=False)
    return config_path
