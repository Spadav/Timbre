from timbre.config import parse_config
from timbre.models import get_profile, model_records, set_active_model


def test_model_profiles_include_local_paths() -> None:
    profile = get_profile("parakeet:int8")

    assert profile.backend == "parakeet"
    assert str(profile.path).endswith(".config/timbre/models/parakeet/int8")
    assert profile.options["model_path"] == str(profile.path)


def test_set_active_model_updates_backend_options_and_default() -> None:
    config = parse_config({})

    set_active_model(config, "whisper:small")

    assert config.stt.default == "whisper"
    assert config.stt.backends["whisper"].options["model_size"] == "small"
    assert str(config.stt.backends["whisper"].options["model_path"]).endswith(
        ".config/timbre/models/whisper/small"
    )


def test_model_records_mark_active_profile() -> None:
    config = parse_config({})

    records = model_records(config)

    active = [record["id"] for record in records if record["active"]]
    assert "whisper:base" in active
    assert "parakeet:int8" not in active
