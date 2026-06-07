# Unified Voice Gateway — Implementation Plan (v1)

## What this is

A single, always-on, OpenAI-compatible audio service that fronts multiple swappable
STT and TTS backends. One URL, one config. Drop it into any OpenAI-compatible client
(Hermes, Open WebUI, SillyTavern, custom agents) and it just works.

Think "llama-swap, but for audio." The HTTP server is always up and reachable; the
heavy model weights load on demand and unload after a per-backend TTL.

Built from scratch (FastAPI + backend libraries as dependencies). NOT a wrapper around
existing audio servers — backends are imported/invoked as libraries, and the API
surface, routing, TTL manager, voice management, and UI are all original.

## v1 scope (locked)

- STT backends: faster-whisper, Parakeet (ONNX)
- TTS backends: PocketTTS, Supertonic
- OpenAI-compatible endpoints (non-streaming): `/v1/audio/speech`, `/v1/audio/transcriptions`
- Discovery endpoints: `/v1/models`, `/v1/voices`, `/health`, `/v1/backends`
- Backend selected via the `model` field in the request
- Voice cloning: upload / list / delete reference audio; cloned voice referenced by name
  in the `voice` field of a speech request
- Per-backend TTL: model weights load on first request, unload after idle TTL.
  TTL = 0 means never unload (keep warm).
- YAML config + first-run setup wizard
- Gradio UI for testing/management (simple, v1)
- Cross-platform: Windows + Linux
- Distribution: pip package AND Docker image

## Out of scope for v1 (note as TODO, do not build)

- Streaming audio output (SSE/chunked)
- Qwen3-TTS backend (heavy torch + compile warmup; add in v2)
- whisper.cpp / parakeet.cpp native binary backends (v2)
- Kokoro / Piper TTS backends (v2)
- Hermes plugin + `/voice-setup` slash command (separate follow-up project)
- Auth / multi-user / rate limiting

## Confirmed compatibility facts (use these, do not re-derive)

- **Python: pin to 3.12.** CTranslate2 (faster-whisper) has lagging wheel support on
  newer Python versions. 3.12 is the safe target.
- **PocketTTS**: pip install `pocket-tts`, pure Python, CPU-first, GPU optional,
  Windows/Linux/macOS, Py 3.10–3.14. Handles its own model download. Voice cloning
  from a 5–10s sample; can export a voice embedding (safetensors) for fast loading.
- **Supertonic**: pip install `supertonic` (or `supertonic[serve]`), ONNX Runtime,
  ~99M params, CPU-first, cross-platform. Models stored on HuggingFace via **Git LFS** —
  the setup flow must download ONNX models + preset voices, not assume pip pulls weights.
  Has native voice cloning via Voice Builder JSON import. Already exposes an
  OpenAI-compatible `/v1/audio/speech` — useful reference for matching request/response.
- **faster-whisper**: pip install `faster-whisper`, CTranslate2 backend, cross-platform
  (x86-64 + ARM64), CPU clean. Auto-downloads CTranslate2 models from HF on first use.
  GPU mode needs cuBLAS/cuDNN on host.
- **Parakeet (ONNX)**: onnxruntime + Parakeet ONNX model. Models on HuggingFace via
  Git LFS — setup must handle download. CPU via onnxruntime, GPU via onnxruntime-gpu.

Model acquisition differs per backend — the setup/install flow must handle each path
(HF Git LFS download for Supertonic + Parakeet; auto-download for whisper + pocket).

## Architecture

```
voice-gateway/
├── pyproject.toml          # package, optional-deps groups, CLI entry point
├── README.md
├── Dockerfile
├── docker-compose.yml      # optional convenience
├── src/voicegateway/
│   ├── __init__.py
│   ├── cli.py              # `serve`, `setup` (wizard), `download-models`
│   ├── config.py           # load/validate YAML; default paths
│   ├── server.py           # FastAPI app factory, mounts routers + Gradio
│   ├── manager.py          # BackendManager: registry + TTL load/unload
│   ├── api/
│   │   ├── speech.py       # POST /v1/audio/speech
│   │   ├── transcribe.py   # POST /v1/audio/transcriptions
│   │   ├── discovery.py    # GET /v1/models, /v1/voices, /v1/backends, /health
│   │   └── voices.py       # POST/GET/DELETE voice clone management
│   ├── backends/
│   │   ├── base.py         # TTSBackend, STTBackend ABCs
│   │   ├── registry.py     # name -> backend class mapping
│   │   ├── tts/
│   │   │   ├── pocket.py
│   │   │   └── supertonic.py
│   │   └── stt/
│   │       ├── whisper.py
│   │       └── parakeet.py
│   ├── voices/             # voice clone storage helpers
│   └── web/                # Gradio UI
└── tests/
```

### Backend ABCs (the core abstraction — own this)

```python
class TTSBackend(ABC):
    name: str
    def __init__(self, config: dict): ...
    async def _ensure_loaded(self): ...      # load weights if not loaded; touch last_used
    async def synthesize(self, text: str, voice: str, **opts) -> bytes: ...  # returns audio bytes
    async def maybe_unload(self, ttl: int): ...  # drop weights if idle past ttl
    @property
    def voices(self) -> list[str]: ...        # preset + cloned voice names
    @property
    def loaded(self) -> bool: ...

class STTBackend(ABC):
    name: str
    def __init__(self, config: dict): ...
    async def _ensure_loaded(self): ...
    async def transcribe(self, audio: bytes, **opts) -> str: ...
    async def maybe_unload(self, ttl: int): ...
    @property
    def loaded(self) -> bool: ...
```

Adding a backend later = implement the ABC + register in `registry.py`. The router and
API never change.

### BackendManager (TTL is the headline feature)

- Holds the registry of all configured backends (objects always alive — cheap).
- On request: `get(name)` -> ensures the backend's **model weights** are loaded, updates
  `last_used`, returns the backend. A per-backend `asyncio.Lock` prevents double-load on
  concurrent cold requests.
- Background task (every N seconds) iterates configured backends and calls
  `maybe_unload(ttl)`; `ttl=0` => never unload.
- IMPORTANT terminology: TTL applies to **model weights**, not the backend object. The
  backend object stays registered and reachable forever; only weights cycle in/out.
- After unload: drop model refs, `gc.collect()`, and for CUDA backends call
  `torch.cuda.empty_cache()` / release the onnxruntime session so VRAM is actually freed.

### Request routing

- `POST /v1/audio/speech`: read `model` field -> resolve to a TTS backend name. `voice`
  field -> preset name or cloned-voice name. `response_format` (mp3/wav/opus/ogg) ->
  convert via ffmpeg/pydub. Return audio bytes with correct content-type.
- `POST /v1/audio/transcriptions`: multipart file upload + `model` field -> resolve to an
  STT backend. Return `{"text": "..."}` (OpenAI shape).
- Unknown `model` -> 400 with a helpful message listing available backends.

### Voice cloning

- Storage dir: `~/.config/voice-gateway/voices/<name>/` (configurable). Store reference
  audio + any derived embedding (e.g. PocketTTS safetensors export, Supertonic Voice
  Builder JSON).
- `POST /v1/voices` (multipart: name + audio file) -> validate, store, optionally
  pre-compute embedding. `GET /v1/voices` -> list. `DELETE /v1/voices/{name}`.
- At synth time, if `voice` matches a cloned name, the backend loads that reference/
  embedding. Each backend implements its own clone-loading path behind a common method.
- Surface cloned voices in `/v1/voices` alongside presets so clients can discover them.

## Config (YAML)

`~/.config/voice-gateway/config.yaml`:

```yaml
server:
  host: 0.0.0.0
  port: 8890
  ttl_check_interval: 30   # seconds between idle sweeps

tts:
  default: pocket
  backends:
    pocket:
      enabled: true
      device: cpu
      ttl: 0               # cheap on CPU, keep warm
    supertonic:
      enabled: true
      device: cpu
      model_path: ~/.config/voice-gateway/models/supertonic
      ttl: 300

stt:
  default: parakeet
  backends:
    whisper:
      enabled: true
      device: cpu
      model_size: base     # tiny/base/small/medium/large-v3
      ttl: 300
    parakeet:
      enabled: true
      device: cpu
      model_path: ~/.config/voice-gateway/models/parakeet
      ttl: 300

voices:
  dir: ~/.config/voice-gateway/voices
```

- `device` per backend: `cpu`, `cuda`, `cuda:0`, `cuda:1`.
- Setup wizard only offers backends whose optional deps are installed.

## Distribution

### pip (optional-dependency groups)

```
pip install voice-gateway              # core (FastAPI, uvicorn, pydub) + pocket + whisper
pip install voice-gateway[parakeet]    # + onnxruntime + parakeet support
pip install voice-gateway[supertonic]  # + supertonic
pip install voice-gateway[gpu]         # onnxruntime-gpu, CUDA-enabled extras
pip install voice-gateway[all]
```

- CLI entry point: `voice-gateway = voicegateway.cli:main`
- Commands: `voice-gateway setup`, `voice-gateway serve`, `voice-gateway download-models`

### Setup wizard (`voice-gateway setup`)

Interactive, writes config.yaml:
- detect installed optional deps -> offer only available backends
- detect CUDA availability -> offer cpu/cuda per backend
- pick default STT + default TTS, port
- offer to download required models now (`download-models`)

### Docker

- Base image: `python:3.12-slim`
- One image with everything, OR `:cpu` and `:cuda` variants (start with one image,
  config decides what loads).
- Install ffmpeg in the image (audio format conversion).
- Volume-mount `~/.config/voice-gateway` for config + models + voices persistence.
- `docker run -p 8890:8890 -v vg-data:/root/.config/voice-gateway voice-gateway`

## Build order (for Codex — do in this sequence)

1. Project skeleton: pyproject.toml (Py 3.12, optional-deps groups, entry point),
   package layout, README stub.
2. config.py: dataclass/pydantic models for the YAML schema above + loader + defaults.
3. backends/base.py: the two ABCs.
4. manager.py: BackendManager with registry, per-backend async lock, TTL background
   sweep. Unit-test with a fake/mock backend before touching real models.
5. api/discovery.py + server.py: get a server up that lists backends and serves /health
   with zero real models loaded.
6. backends/tts/pocket.py: first real backend. Wire `/v1/audio/speech` end to end
   (non-streaming, wav out, then add format conversion).
7. backends/stt/whisper.py: first real STT. Wire `/v1/audio/transcriptions` end to end.
8. backends/tts/supertonic.py + backends/stt/parakeet.py: remaining backends, including
   their HF Git LFS model-download paths in `download-models`.
9. Voice cloning: voices.py + storage + per-backend clone-loading. Wire into
   `/v1/audio/speech` and `/v1/voices`.
10. cli.py setup wizard + download-models command.
11. Gradio UI: pick backend, type text -> hear audio; upload audio -> see transcript;
    manage cloned voices; show which models are currently loaded (live TTL state).
12. Dockerfile + docker-compose, ffmpeg, volume.
13. Tests: backend ABC conformance, TTL load/unload, format conversion, OpenAI-shape
    responses, unknown-model errors. README with quickstart for both pip and Docker.

## Acceptance criteria (v1 done when)

- Server starts with no models loaded and stays reachable; `/health` and `/v1/backends`
  respond instantly.
- A speech request to a cold backend loads weights, returns valid audio, and the model
  unloads after its TTL (verify VRAM/RAM actually drops for a cuda backend).
- A transcription request returns correct text from an uploaded audio file.
- Backend is selectable via `model`; bad model returns a clear 400.
- Voice clone: upload reference -> request that voice by name -> audio uses the clone.
- `response_format` conversions work (at least wav, mp3, opus/ogg) since Hermes wants opus.
- Works on both Windows and Linux from a clean `pip install` (CPU path), and from Docker.
- A real OpenAI-compatible client (point Hermes `tts.openai.base_url` /
  `STT_OPENAI_BASE_URL` at it) drives both TTS and STT successfully.

## Notes / gotchas to hand to Codex

- TTL frees **weights**, never the backend object or the server.
- Concurrent cold-start requests to one backend must trigger a single load (per-backend
  lock).
- CUDA cleanup on unload must actually release VRAM (empty_cache / dispose ORT session).
- Supertonic + Parakeet need Git LFS / HF model downloads handled explicitly; don't
  assume pip ships the weights.
- Match OpenAI request/response shapes exactly (field names, multipart for transcription,
  `{"text": ...}` response) so existing clients work unmodified.
- Keep the backend ABC strict and minimal so v2 backends (Qwen, Kokoro, whisper.cpp,
  parakeet.cpp) slot in without touching router/API.
```
