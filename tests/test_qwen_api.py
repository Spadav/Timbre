from timbre.api.qwen import (
    QwenCloneSpeechRequest,
    QwenVoiceDesignSpeechRequest,
    _generation_overrides,
)


def test_qwen_clone_generation_overrides_keep_explicit_false() -> None:
    payload = QwenCloneSpeechRequest(
        input="Hello",
        voice="sample",
        temperature=0.7,
        do_sample=False,
        subtalker_dosample=False,
    )

    assert _generation_overrides(payload) == {
        "temperature": 0.7,
        "do_sample": False,
        "subtalker_dosample": False,
    }


def test_qwen_voice_design_omits_unspecified_generation_options() -> None:
    payload = QwenVoiceDesignSpeechRequest(input="Hello", instruct="A calm narrator")

    assert _generation_overrides(payload) == {}
