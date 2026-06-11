# hermes-timbre

Hermes Agent plugin for Timbre, a local OpenAI-compatible voice gateway.

The plugin registers `timbre` as both a Hermes TTS provider and STT provider.
It is only an HTTP client. It does not import Timbre, PocketTTS, Parakeet,
ONNX, Torch, or any model runtime.

## Install

```bash
hermes plugins install Spadav/hermes-timbre
hermes plugins enable hermes-timbre
```

Or install with pip:

```bash
pip install hermes-timbre
hermes plugins enable hermes-timbre
```

## Configure

Inside Hermes:

```text
/timbre http://127.0.0.1:9000
/timbre http://100.112.50.55:9000 --tts pocket --stt parakeet --voice alba
```

The command checks `/health`, discovers `/v1/backends`, saves the plugin config
to `~/.hermes/hermes-timbre.json`, and tries to set these Hermes config values:

```yaml
tts:
  provider: timbre
stt:
  provider: timbre
```

Status commands:

```text
/timbre status
/timbre backends
```

Optional CLI commands, if supported by your Hermes build:

```bash
hermes timbre setup http://127.0.0.1:9000 --tts pocket --stt parakeet
hermes timbre status
hermes timbre backends
```

## Environment Overrides

These override the saved config:

```bash
export TIMBRE_URL=http://127.0.0.1:9000
export TIMBRE_TTS_BACKEND=pocket
export TIMBRE_STT_BACKEND=parakeet
export TIMBRE_TTS_VOICE=alba
```

## Behavior

TTS calls go to:

```text
POST {TIMBRE_URL}/v1/audio/speech
```

STT calls go to:

```text
POST {TIMBRE_URL}/v1/audio/transcriptions
```

The Hermes provider name is always `timbre`. The Timbre backend is selected by
the plugin config:

- TTS default backend: `pocket`
- STT default backend: `parakeet`
- TTS default voice: `alba`

Timbre handles model loading, voice aliases, cloned voices, audio conversion,
and backend runtime state.
