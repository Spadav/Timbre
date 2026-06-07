from __future__ import annotations

from io import BytesIO

from fastapi import HTTPException
from pydub import AudioSegment

MEDIA_TYPES = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "ogg": "audio/ogg",
    "opus": "audio/opus",
    "flac": "audio/flac",
}


def media_type_for(fmt: str) -> str:
    return MEDIA_TYPES.get(fmt, "application/octet-stream")


def convert_audio(audio: bytes, source_format: str, target_format: str) -> bytes:
    target = target_format.lower()
    if target == source_format.lower():
        return audio
    try:
        segment = AudioSegment.from_file(BytesIO(audio), format=source_format)
        output = BytesIO()
        export_format = "ogg" if target == "opus" else target
        codec = "libopus" if target == "opus" else None
        segment.export(output, format=export_format, codec=codec)
        return output.getvalue()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Audio conversion to {target_format} failed. Ensure ffmpeg is installed.",
        ) from exc
