"""Separate, console-less speech worker built as its own PyInstaller EXE.

Usage: DonathonSpeechWorker.exe --job C:\\path\\to\\job.json
Writes JSON status lines to stdout for the GUI to consume.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from src.donathon.storage import Storage


def emit(code: str, message: str) -> None:
    sys.stdout.write(json.dumps({"code": code, "text": message}, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    args = parser.parse_args()
    job = json.loads(Path(args.job).read_text(encoding="utf-8"))
    from faster_whisper import WhisperModel

    model_name = str(job.get("model") or "base")
    if model_name not in {"tiny", "base", "small"}:
        raise ValueError("Invalid speech model")
    storage = Storage(Path(job["db_path"]))
    # Keep STT from competing aggressively with games/OBS.
    threads = max(1, min(2, (os.cpu_count() or 2) // 2 or 1))
    emit("progress", "Загружаю модель речи (при первом запуске нужен интернет)…")
    model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=threads)
    recordings = job["recordings"]
    for index, rec in enumerate(recordings, start=1):
        emit("progress", f"Распознаю речь · файл {index} из {len(recordings)}")
        segments, _ = model.transcribe(
            rec["path"], language="ru", vad_filter=True, beam_size=1,
            condition_on_previous_text=False,
        )
        for segment in segments:
            spoken = str(segment.text or "").strip()
            if spoken:
                storage.add_speech_segment(
                    int(job["profile_id"]), session_id=int(job["session_id"]),
                    recording_id=int(rec["id"]),
                    started_at=float(rec["started_at"]) + float(segment.start),
                    ended_at=float(rec["started_at"]) + float(segment.end),
                    text=spoken,
                )
        storage.finish_speech_recording(int(rec["id"]), float(rec.get("ended_at") or time.time()), "transcribed")
        if job.get("delete_audio"):
            try:
                Path(rec["path"]).unlink(missing_ok=True)
            except OSError:
                pass
    emit("done", "Готово — текст появился в Анализе")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        emit("error", f"Ошибка распознавания: {exc}")
        raise SystemExit(1)
