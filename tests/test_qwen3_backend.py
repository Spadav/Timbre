from __future__ import annotations

from pathlib import Path
from typing import Any

from timbre.backends.tts.qwen3 import (
    DEFAULT_QWEN3_VOICES,
    Qwen3Backend,
    _generate_native,
    _model_source,
)


def test_qwen3_native_voices_do_not_include_openai_aliases() -> None:
    voices = Qwen3Backend({"model_type": "customvoice"}).voices

    assert "Vivian" in voices
    assert "alloy" not in voices
    assert set(DEFAULT_QWEN3_VOICES).issubset(voices)


def test_qwen3_base_model_lists_uploaded_clones(tmp_path: Path) -> None:
    voice_dir = tmp_path / "sample_clone"
    voice_dir.mkdir()
    (voice_dir / "reference.wav").write_bytes(b"RIFF....WAVE")

    voices = Qwen3Backend({"model_type": "base"}, voices_dir=str(tmp_path)).voices

    assert voices == ["sample_clone"]


def test_qwen3_uses_local_model_path_when_installed(tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}", encoding="utf-8")

    source = _model_source(
        {
            "model": "1.7b-customvoice",
            "repo_id": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
            "model_path": str(model_dir),
        }
    )

    assert source == str(model_dir)


def test_qwen3_native_generation_maps_default_voice() -> None:
    class FakeModel:
        def generate_custom_voice(self, **kwargs: Any) -> tuple[list[list[float]], int]:
            assert kwargs["speaker"] == "Vivian"
            assert kwargs["text"] == "hello"
            assert kwargs["language"] == "Auto"
            return [[0.0, 0.25, -0.25]], 24000

    audio, sample_rate = _generate_native(FakeModel(), "hello", "default", "Auto", None, 1.0)

    assert audio == [0.0, 0.25, -0.25]
    assert sample_rate == 24000
