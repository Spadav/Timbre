import pytest
from httpx import ASGITransport, AsyncClient

from timbre.backends.base import TTSBackend
from timbre.config import default_config
from timbre.server import create_app


class RecordingTTS(TTSBackend):
    name = "recording"

    async def _load(self) -> None:
        self.config["loaded"] = True

    async def synthesize(self, text: str, voice: str, **opts) -> bytes:
        self.config["last_voice"] = voice
        return b"RIFF....WAVE"


@pytest.mark.asyncio
async def test_health_and_backends_respond_without_loading_models() -> None:
    config = default_config()
    config.tts.backends["pocket"].enabled = False
    config.tts.backends["supertonic"].enabled = False
    config.stt.backends["whisper"].enabled = False
    config.stt.backends["parakeet"].enabled = False

    async with AsyncClient(
        transport=ASGITransport(app=create_app(config)), base_url="http://test"
    ) as client:
        assert (await client.get("/health")).json()["status"] == "ok"
        states = (await client.get("/v1/backends")).json()["data"]
        assert len(states) == 5
        assert all(item["enabled"] is False and item["loaded"] is False for item in states)


@pytest.mark.asyncio
async def test_ui_is_served_when_dist_exists() -> None:
    config = default_config()

    async with AsyncClient(
        transport=ASGITransport(app=create_app(config)), base_url="http://test"
    ) as client:
        response = await client.get("/ui/")
        assert response.status_code == 200
        assert "Timbre" in response.text


@pytest.mark.asyncio
async def test_config_is_exposed() -> None:
    config = default_config()

    async with AsyncClient(
        transport=ASGITransport(app=create_app(config)), base_url="http://test"
    ) as client:
        response = await client.get("/v1/config")
        assert response.status_code == 200
        body = response.json()
        assert body["config"]["server"]["port"] == 9000
        assert "pocket" in body["config"]["tts"]["backends"]


@pytest.mark.asyncio
async def test_backend_enable_disable_updates_config(tmp_path) -> None:
    config = default_config()
    config.tts.backends["pocket"].enabled = True
    app = create_app(config)
    app.state.config_path = tmp_path / "config.yaml"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/backends/tts/pocket", json={"action": "disable"})
        assert response.status_code == 200
        states = response.json()["data"]
        pocket = next(item for item in states if item["kind"] == "tts" and item["name"] == "pocket")
        assert pocket["enabled"] is False
        assert pocket["loaded"] is False

        response = await client.post("/v1/backends/tts/pocket", json={"action": "enable"})
        assert response.status_code == 200
        states = response.json()["data"]
        pocket = next(item for item in states if item["kind"] == "tts" and item["name"] == "pocket")
        assert pocket["enabled"] is True


@pytest.mark.asyncio
async def test_cloned_voice_reference_is_served(tmp_path) -> None:
    config = default_config()
    config.voices.dir = tmp_path / "voices"
    app = create_app(config)
    voice_dir = config.voices.dir / "sample_clone"
    voice_dir.mkdir(parents=True)
    (voice_dir / "reference.wav").write_bytes(b"RIFFtestWAVE")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/voices/sample_clone/reference")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("audio/wav")
        assert response.content == b"RIFFtestWAVE"


@pytest.mark.asyncio
async def test_voice_aliases_are_listed_and_mutable(tmp_path) -> None:
    config = default_config()
    config.tts.backends["pocket"].enabled = False
    config.tts.backends["supertonic"].enabled = False
    app = create_app(config)
    app.state.config_path = tmp_path / "config.yaml"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/voices")
        assert response.status_code == 200
        aliases = [item for item in response.json()["data"] if item["type"] == "alias"]
        assert {"name": "alloy", "backend": "supertonic", "target": "F1", "type": "alias"} in aliases

        response = await client.post(
            "/v1/voices/aliases",
            json={"backend": "pocket", "alias": "reader", "target": "alba"},
        )
        assert response.status_code == 200
        aliases = [item for item in response.json()["data"] if item["type"] == "alias"]
        assert {"name": "reader", "backend": "pocket", "target": "alba", "type": "alias"} in aliases

        response = await client.delete("/v1/voices/aliases/pocket/reader")
        assert response.status_code == 200
        aliases = [item for item in response.json()["data"] if item["type"] == "alias"]
        assert not any(item["name"] == "reader" and item["backend"] == "pocket" for item in aliases)


@pytest.mark.asyncio
async def test_speech_resolves_voice_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    import timbre.manager as manager_module

    monkeypatch.setitem(manager_module.TTS_BACKENDS, "recording", RecordingTTS)
    config = default_config()
    config.tts.default = "recording"
    config.tts.backends = {"recording": config.tts.backends["pocket"]}
    config.voices.aliases = {"recording": {"friendly": "native"}}
    app = create_app(config)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/audio/speech",
            json={"model": "recording", "input": "hello", "voice": "friendly"},
        )
        assert response.status_code == 200
        assert app.state.manager.tts["recording"].config["last_voice"] == "native"
