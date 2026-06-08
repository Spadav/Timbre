from timbre.backends.tts.supertonic import SupertonicBackend


def test_supertonic_exposes_native_and_openai_alias_voices() -> None:
    voices = SupertonicBackend({}).voices

    assert "default" in voices
    assert "alloy" in voices
    assert "echo" in voices
    assert "M5" in voices
    assert "F5" in voices
