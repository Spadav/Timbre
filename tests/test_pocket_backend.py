from __future__ import annotations

from timbre.backends.tts.pocket import _generation_kwargs


def test_pocket_uses_upstream_safe_chunk_size_by_default() -> None:
    assert _generation_kwargs({}, {}) == {"max_tokens": 50}


def test_pocket_generation_options_override_defaults() -> None:
    assert _generation_kwargs(
        {"max_tokens": 50},
        {"max_tokens": 80, "frames_after_eos": 3},
    ) == {"max_tokens": 80, "frames_after_eos": 3}
