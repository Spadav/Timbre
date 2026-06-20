from __future__ import annotations

from pathlib import Path
from typing import Any

from timbre.backends.tts.qwen3 import (
    DEFAULT_QWEN3_VOICES,
    Qwen3Backend,
    _best_cuda_device,
    _generate_native,
    _generation_kwargs,
    _model_source,
    _resolve_device,
    _split_text,
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


def test_qwen3_generation_kwargs_forward_configured_values() -> None:
    kwargs = _generation_kwargs(
        {
            "temperature": 0.8,
            "top_p": 0.92,
            "max_new_tokens": 2048,
            "repetition_penalty": 1.08,
            "do_sample": "true",
        }
    )

    assert kwargs == {
        "temperature": 0.8,
        "top_p": 0.92,
        "max_new_tokens": 2048,
        "repetition_penalty": 1.08,
        "do_sample": True,
    }


def test_qwen3_generation_kwargs_request_values_override_global_config() -> None:
    kwargs = _generation_kwargs(
        {
            "temperature": 0.9,
            "top_p": 1.0,
            "do_sample": True,
            "subtalker_dosample": True,
        },
        {
            "temperature": 0.65,
            "do_sample": False,
            "subtalker_dosample": False,
        },
    )

    assert kwargs["temperature"] == 0.65
    assert kwargs["top_p"] == 1.0
    assert kwargs["do_sample"] is False
    assert kwargs["subtalker_dosample"] is False


def test_qwen3_split_text_respects_chunk_limit() -> None:
    chunks = _split_text("First sentence. Second sentence is longer. Third.", 24)

    assert all(len(chunk) <= 24 for chunk in chunks)
    assert chunks[0] == "First sentence."
    assert chunks[-1] == "Third."


def test_qwen3_resolves_auto_cuda_to_gpu_with_most_free_memory() -> None:
    class FakeCuda:
        def __init__(self) -> None:
            self.current = 0

        def is_available(self) -> bool:
            return True

        def device_count(self) -> int:
            return 2

        def device(self, index: int) -> "FakeCuda":
            self.current = index
            return self

        def __enter__(self) -> None:
            return None

        def __exit__(self, *args: Any) -> None:
            return None

        def mem_get_info(self) -> tuple[int, int]:
            return [(2, 10), (18, 24)][self.current]

    fake_torch = type("FakeTorch", (), {"cuda": FakeCuda()})()

    assert _resolve_device("cuda:auto", fake_torch) == "cuda:1"
    assert _resolve_device("cuda", fake_torch) == "cuda:1"
    assert _best_cuda_device(fake_torch) == "cuda:1"


def test_qwen3_keeps_explicit_cuda_device() -> None:
    class FakeCuda:
        def is_available(self) -> bool:
            return True

    fake_torch = type("FakeTorch", (), {"cuda": FakeCuda()})()

    assert _resolve_device("cuda:1", fake_torch) == "cuda:1"
