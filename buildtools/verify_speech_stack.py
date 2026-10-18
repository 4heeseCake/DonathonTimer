"""Build-time self-test for speech decoding; no model download, no network needed.

The error `open() got an unexpected keyword argument metadata_errors` was
caused by faster-whisper 1.2.1 calling PyAV 19 with a removed keyword.
This exercises the exact decode_audio path so incompatible builds cannot ship.
"""
from __future__ import annotations

import math
import struct
import tempfile
import wave
from pathlib import Path
from importlib.metadata import version


def check() -> None:
    import av
    from faster_whisper.audio import decode_audio

    av_version = version("av")
    whisper_version = version("faster-whisper")
    print(f"Checking STT: PyAV={av_version}, faster-whisper={whisper_version}", flush=True)
    if av_version != "17.1.0":
        raise RuntimeError(f"Expected compatible PyAV 17.1.0, got {av_version}")
    with tempfile.TemporaryDirectory() as folder:
        filename = Path(folder) / "speech-audio-test.wav"
        # A real, generated 16kHz mono PCM wave; no user's microphone/data used.
        rate = 16000
        data = b"".join(
            struct.pack("<h", int(3000 * math.sin(2 * math.pi * 440 * t / rate)))
            for t in range(rate // 5)
        )
        with wave.open(str(filename), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(rate)
            out.writeframes(data)
        with av.open(str(filename), mode="r", metadata_errors="ignore") as container:
            if not container.streams.audio:
                raise RuntimeError("PyAV could not decode WAV audio")
        decoded = decode_audio(str(filename))
        if len(decoded) == 0:
            raise RuntimeError("faster-whisper decoded empty audio")
        print("STT audio decoder OK", flush=True)


if __name__ == "__main__":
    check()
