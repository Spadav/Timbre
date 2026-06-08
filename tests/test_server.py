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
        assert (await client.get("/v1/backends")).json() == {"data": []}


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
