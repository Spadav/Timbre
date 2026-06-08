from timbre.backends.tts.supertonic import SupertonicBackend


def test_supertonic_exposes_native_voices() -> None:
    voices = SupertonicBackend({}).voices

    assert "default" in voices
    assert "alloy" not in voices
    assert "echo" not in voices
    assert "M5" in voices
    assert "F5" in voices
    assert len([voice for voice in voices if voice != "default"]) == 10
