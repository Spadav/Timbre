from fastapi.testclient import TestClient

from timbre.config import default_config
from timbre.server import create_app


def test_health_and_backends_respond_without_loading_models() -> None:
    config = default_config()
    config.tts.backends["pocket"].enabled = False
    config.tts.backends["supertonic"].enabled = False
    config.stt.backends["whisper"].enabled = False
    config.stt.backends["parakeet"].enabled = False

    with TestClient(create_app(config)) as client:
        assert client.get("/health").json()["status"] == "ok"
        assert client.get("/v1/backends").json() == {"data": []}
