from timbre.backends.stt import parakeet


def test_parakeet_intra_threads_default_to_cpu_capacity(monkeypatch) -> None:
    monkeypatch.setattr(parakeet, "_physical_cpu_count", lambda: 12)
    monkeypatch.setattr(parakeet, "_available_logical_cpus", lambda: 20)

    assert parakeet._default_ort_intra_threads() == 12
    assert parakeet._thread_count(None, parakeet._default_ort_intra_threads()) == 12
    assert parakeet._thread_count("auto", parakeet._default_ort_intra_threads()) == 12


def test_parakeet_thread_count_accepts_explicit_override() -> None:
    assert parakeet._thread_count(4, 12) == 4
    assert parakeet._thread_count("6", 12) == 6
    assert parakeet._thread_count("bad", 12) == 12
