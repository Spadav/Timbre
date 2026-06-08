import pytest
from httpx import ASGITransport, AsyncClient

from timbre.config import default_config
from timbre.server import create_app


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
        assert len(states) == 4
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
    voice_dir = config.voices.dir / "aria"
    voice_dir.mkdir(parents=True)
    (voice_dir / "reference.wav").write_bytes(b"RIFFtestWAVE")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/voices/aria/reference")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("audio/wav")
        assert response.content == b"RIFFtestWAVE"
