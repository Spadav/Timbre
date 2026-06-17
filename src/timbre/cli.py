from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn
import yaml

from timbre.config import CONFIG_PATH, dump_config, load_config, write_default_config
from timbre.models import download_model, model_profiles, set_active_model
from timbre.server import create_app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="timbre")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve", help="Run the Timbre HTTP server.")
    serve_parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    serve_parser.add_argument("--host")
    serve_parser.add_argument("--port", type=int)
    serve_parser.add_argument("--access-log", action="store_true", help="Enable raw HTTP access logs.")

    setup_parser = subparsers.add_parser("setup", help="Write a default config file.")
    setup_parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    setup_parser.add_argument("--overwrite", action="store_true")

    download_parser = subparsers.add_parser(
        "download-models", help="Download model files managed outside pip."
    )
    download_parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    download_parser.add_argument(
        "--backend", choices=["supertonic", "parakeet", "whisper", "qwen3", "all"], default="all"
    )
    download_parser.add_argument("--model", help="Model profile id, for example parakeet:int8.")
    download_parser.add_argument("--set-default", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "setup":
        path = write_default_config(args.config, overwrite=args.overwrite)
        print(f"Wrote config: {path}")
        return
    if args.command == "serve":
        config = load_config(args.config)
        host = args.host or config.server.host
        port = args.port or config.server.port
        uvicorn.run(create_app(config), host=host, port=port, access_log=args.access_log)
        return
    if args.command == "download-models":
        download_models(args.config, args.backend, args.model, args.set_default)


def download_models(config_path: Path, backend: str, model: str | None, set_default: bool) -> None:
    config = load_config(config_path)
    if model:
        profiles = [profile for profile in model_profiles() if profile.id == model]
    else:
        profiles = [
            profile
            for profile in model_profiles()
            if profile.downloadable and (backend == "all" or profile.backend == backend)
        ]
    if not profiles:
        available = ", ".join(profile.id for profile in model_profiles())
        raise SystemExit(f"No matching model profiles. Available: {available}")
    for profile in profiles:
        path = download_model(profile.id)
        print(f"Downloaded {profile.id} to: {path}")
        if set_default:
            config = set_active_model(config, profile.id)
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with config_path.open("w", encoding="utf-8") as handle:
                yaml.safe_dump(dump_config(config), handle, sort_keys=False)
