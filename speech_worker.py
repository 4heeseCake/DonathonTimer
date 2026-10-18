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
import wave
from pathlib import Path

from src.donathon.storage import Storage


def emit(code: str, message: str, progress: int | None = None) -> None:
    # JSON escaping makes the wire protocol ASCII-only: Windows console code
    # pages (cp1251/cp866) cannot corrupt Russian progress/error messages.
    data = {"code": code, "text": message}
    if progress is not None:
        data["progress"] = max(0, min(100, int(progress)))
    sys.stdout.write(json.dumps(data, ensure_ascii=True) + "\n")
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
    recordings = job["recordings"]
    if not recordings:
        emit("error", "У этой сессии нет сохранённых аудиозаписей. Проверь включение записи и микрофон.")
        return 1
    for rec in recordings:
        audio = Path(rec["path"])
        if not audio.is_file() or audio.stat().st_size < 64:
            emit("error", "Аудиозапись не найдена или пуста. Создай новую сессию с включённой записью.")
            return 1

    # Keep STT from competing aggressively with games/OBS.
    threads = max(1, min(2, (os.cpu_count() or 2) // 2 or 1))
    emit("progress", "Подготавливаю модель речи. При первом запуске возможна загрузка из интернета…", 3)
    model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=threads)
    emit("progress", "Модель готова. Начинаю слушать запись…", 10)
    word_found = False
    for index, rec in enumerate(recordings, start=1):
        duration = 1.0
        try:
            with wave.open(str(rec["path"]), "rb") as wav:
                duration = max(1.0, wav.getnframes() / max(1, wav.getframerate()))
        except (wave.Error, OSError):
            pass
        file_fraction = (index - 1) / len(recordings)
        base_progress = 10 + int(85 * file_fraction)
        emit("progress", f"Обрабатываю запись {index} из {len(recordings)}…", base_progress)
        segments, _ = model.transcribe(
            rec["path"], language="ru", vad_filter=True, beam_size=1,
            condition_on_previous_text=False,
        )
        found_in_file = False
        last_reported = -1
        for segment in segments:
            spoken = str(segment.text or "").strip()
            if spoken:
                found_in_file = True
                word_found = True
                storage.add_speech_segment(
                    int(job["profile_id"]), session_id=int(job["session_id"]),
                    recording_id=int(rec["id"]),
                    started_at=float(rec["started_at"]) + float(segment.start),
                    ended_at=float(rec["started_at"]) + float(segment.end),
                    text=spoken,
                )
            ratio = min(1.0, max(0.0, float(segment.end)/duration))
            percentage = min(95, base_progress + int(85 * ratio / len(recordings)))
            if percentage > last_reported:
                emit("progress", f"Распознаю речь: запись {index}/{len(recordings)}, примерно {int(ratio*100)}% записи", percentage)
                last_reported = percentage
        if found_in_file:
            storage.finish_speech_recording(int(rec["id"]), float(rec.get("ended_at") or time.time()), "transcribed")
            if job.get("delete_audio"):
                try:
                    Path(rec["path"]).unlink(missing_ok=True)
                except OSError:
                    pass
        else:
            # Don't discard the recording: it may be the wrong microphone,
            # a silent file, or a too-strict noise filter. Allow retry.
            storage.finish_speech_recording(int(rec["id"]), float(rec.get("ended_at") or time.time()), "error")
        emit("progress", f"Обработано записей: {index} из {len(recordings)}", 10 + int(85*index/len(recordings)))
    if not word_found:
        emit("error", "Запись обработана, но слов не найдено. Проверь микрофон, громкость и попробуй ещё раз.")
        return 2
    emit("done", "Готово! Найденные слова появились в разделе «Речь стримера».", 100)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        emit("error", f"Ошибка распознавания: {exc}")
        raise SystemExit(1)
