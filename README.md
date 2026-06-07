# Timbre

Timbre is an OpenAI-compatible local voice gateway for swappable speech-to-text and
text-to-speech backends.

## Quick Start

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -e ".[all,dev]"
timbre setup
timbre serve
```

Default server: `http://127.0.0.1:9000`

```bash
curl http://127.0.0.1:9000/health
curl http://127.0.0.1:9000/v1/backends
```

Web UI: `http://127.0.0.1:9000/ui/`

The UI source lives in `web/` and is served from the compiled `web/dist` assets:

```bash
cd web
npm install
npm run build
```

## OpenAI-Compatible Endpoints

- `POST /v1/audio/speech`
- `POST /v1/audio/transcriptions`
- `GET /v1/models`
- `GET /v1/voices`
- `GET /v1/backends`
- `GET /health`

## Package Names

- GitHub: `Spadav/Timbre`
- PyPI: `timbre-voice`
- Python import: `timbre`
- CLI: `timbre serve`, `timbre setup`, `timbre download-models`
- Docker: `spadav/timbre`
- Config: `~/.config/timbre/config.yaml`
