from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn
from huggingface_hub import snapshot_download

from timbre.config import CONFIG_PATH, load_config, write_default_config
from timbre.server import create_app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="timbre")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve", help="Run the Timbre HTTP server.")
    serve_parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    serve_parser.add_argument("--host")
    serve_parser.add_argument("--port", type=int)

    setup_parser = subparsers.add_parser("setup", help="Write a default config file.")
    setup_parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    setup_parser.add_argument("--overwrite", action="store_true")

    download_parser = subparsers.add_parser(
        "download-models", help="Download model files managed outside pip."
    )
    download_parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    download_parser.add_argument("--backend", choices=["supertonic", "parakeet", "all"], default="all")

    args = parser.parse_args(argv)
    if args.command == "setup":
        path = write_default_config(args.config, overwrite=args.overwrite)
        print(f"Wrote config: {path}")
        return
    if args.command == "serve":
        config = load_config(args.config)
        host = args.host or config.server.host
        port = args.port or config.server.port
        uvicorn.run(create_app(config), host=host, port=port)
        return
    if args.command == "download-models":
        download_models(args.config, args.backend)


def download_models(config_path: Path, backend: str) -> None:
    config = load_config(config_path)
    if backend in {"supertonic", "all"}:
        supertonic = config.tts.backends.get("supertonic")
        if supertonic and supertonic.options.get("model_path"):
            print("Supertonic downloads its SDK models on first use; no static repo is configured.")
    if backend in {"parakeet", "all"}:
        parakeet = config.stt.backends.get("parakeet")
        if parakeet:
            repo_id = parakeet.options.get("repo_id", "nemo-parakeet-tdt-0.6b-v3")
            model_path = parakeet.options.get("model_path")
            if model_path:
                path = snapshot_download(repo_id=repo_id, local_dir=model_path)
                print(f"Downloaded Parakeet model files to: {path}")
