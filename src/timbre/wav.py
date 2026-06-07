from __future__ import annotations

from io import BytesIO
from typing import Any
import wave


def pcm_wav_bytes(audio: Any, sample_rate: int) -> bytes:
    import numpy as np

    array = np.asarray(audio)
    array = np.squeeze(array)
    if array.ndim == 1:
        channels = 1
    elif array.ndim == 2:
        if array.shape[0] <= 8 and array.shape[1] > array.shape[0]:
            array = array.T
        channels = array.shape[1]
    else:
        raise ValueError(f"Unsupported audio array shape: {array.shape}")

    if np.issubdtype(array.dtype, np.floating):
        array = np.clip(array, -1.0, 1.0)
        array = (array * 32767.0).astype("<i2")
    else:
        array = array.astype("<i2")

    output = BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(array.tobytes())
    return output.getvalue()
