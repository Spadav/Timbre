from timbre.config import parse_config


def test_project_defaults_use_timbre_identity() -> None:
    config = parse_config({})
    assert config.server.port == 9000
    assert str(config.voices.dir).endswith(".config/timbre/voices")


def test_config_overrides_port_and_backend_options() -> None:
    config = parse_config(
        {
            "server": {"port": 9010},
            "stt": {"backends": {"whisper": {"model_size": "tiny", "ttl": 1}}},
        }
    )
    assert config.server.port == 9010
    assert config.stt.backends["whisper"].options["model_size"] == "tiny"
    assert config.stt.backends["whisper"].ttl == 1


def test_supertonic_default_model_is_configurable() -> None:
    config = parse_config({})
    supertonic = config.tts.backends["supertonic"]
    assert supertonic.options["model"] == "supertonic-3"
    assert supertonic.options["steps"] == 8
