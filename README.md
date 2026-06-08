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

### Discovery

```bash
curl http://127.0.0.1:9000/health
curl http://127.0.0.1:9000/v1/models
curl http://127.0.0.1:9000/v1/backends
curl http://127.0.0.1:9000/v1/voices
```

`model` is the backend name. TTS backends include names such as `pocket` and
`supertonic`; STT backends include names such as `parakeet` and `whisper`.

### Text to Speech

```bash
curl http://127.0.0.1:9000/v1/audio/speech \
  -H "content-type: application/json" \
  -d '{
    "model": "pocket",
    "input": "Hello from Timbre.",
    "voice": "aria",
    "response_format": "wav",
    "speed": 1.0,
    "language": "en",
    "steps": 8
  }' \
  --output timbre.wav
```

`response_format` accepts `wav`, `mp3`, `opus`, `ogg`, or `flac`. `language`
and `steps` are backend-specific fields used by Supertonic.

### Speech to Text

```bash
curl http://127.0.0.1:9000/v1/audio/transcriptions \
  -F model=parakeet \
  -F file=@sample.wav
```

Optional form fields: `language` and `prompt`.

### Backend Control

Use `tts` for text-to-speech backends and `stt` for speech-to-text backends.
`load` and `unload` affect runtime memory. `enable` and `disable` update config
and rebuild the backend manager.

```bash
curl http://127.0.0.1:9000/v1/backends/tts/pocket \
  -H "content-type: application/json" \
  -d '{"action":"load"}'

curl http://127.0.0.1:9000/v1/backends/stt/parakeet \
  -H "content-type: application/json" \
  -d '{"action":"unload"}'

curl http://127.0.0.1:9000/v1/backends/tts/supertonic \
  -H "content-type: application/json" \
  -d '{"action":"disable"}'
```

### Voices and Config

```bash
curl http://127.0.0.1:9000/v1/voices \
  -F name=my_voice \
  -F backend=pocket \
  -F precompute=true \
  -F file=@reference.wav

curl http://127.0.0.1:9000/v1/voices/my_voice/reference --output reference.wav
curl -X DELETE http://127.0.0.1:9000/v1/voices/my_voice

curl http://127.0.0.1:9000/v1/config
curl -X PUT http://127.0.0.1:9000/v1/config \
  -H "content-type: application/json" \
  -d @config.json
```

## Package Names

- GitHub: `Spadav/Timbre`
- PyPI: `timbre-voice`
- Python import: `timbre`
- CLI: `timbre serve`, `timbre setup`, `timbre download-models`
- Docker: `spadav/timbre`
- Config: `~/.config/timbre/config.yaml`
