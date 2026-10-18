from __future__ import annotations

import multiprocessing as mp
import json
import tempfile
import os
import queue
import subprocess
import sys
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path

from .config import RECORDINGS_DIR, DATA_DIR
from .speech_component import component_installed, install_component, worker_path
from .state import AppState
from .storage import Storage


@dataclass(slots=True)
class SpeechStatus:
    code: str
    text: str
    progress: int | None = None


def _transcribe_process(
    db_path: str,
    profile_id: int,
    session_id: int,
    recordings: list[dict],
    model_name: str,
    delete_audio: bool,
    progress_queue,
) -> None:
    """Run the heavy speech model in a separate process.

    When the process exits, Windows can release the model/native allocator memory
    completely instead of leaving it inside the long-running GUI process.
    """
    try:
        from faster_whisper import WhisperModel

        storage = Storage(Path(db_path))
        threads = max(1, min(2, (os.cpu_count() or 2) // 2 or 1))
        model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=threads)
        for index, rec in enumerate(recordings, start=1):
            progress_queue.put(("progress", f"Распознаю речь после стрима · {index}/{len(recordings)}"))
            segments, _info = model.transcribe(
                rec["path"],
                language="ru",
                vad_filter=True,
                beam_size=1,
                condition_on_previous_text=False,
            )
            for seg in segments:
                text = str(seg.text or "").strip()
                if not text:
                    continue
                storage.add_speech_segment(
                    profile_id,
                    session_id=session_id,
                    recording_id=rec["id"],
                    started_at=float(rec["started_at"]) + float(seg.start),
                    ended_at=float(rec["started_at"]) + float(seg.end),
                    text=text,
                )
            storage.finish_speech_recording(rec["id"], rec.get("ended_at") or time.time(), "transcribed")
            if delete_audio:
                try:
                    Path(rec["path"]).unlink(missing_ok=True)
                except Exception:
                    pass
        progress_queue.put(("done", "Готово! Распознанные слова появились в Анализе."))
    except Exception as exc:
        progress_queue.put(("error", f"Ошибка распознавания речи: {exc}"))


class SpeechService:
    """Low-overhead microphone capture with optional post-stream transcription."""

    def __init__(self, state: AppState, storage: Storage):
        self.state = state
        self.storage = storage
        self._lock = threading.RLock()
        self._status = SpeechStatus("idle", "Анализ речи выключен")
        self._stream = None
        self._writer_thread: threading.Thread | None = None
        self._queue: queue.Queue[bytes | None] = queue.Queue(maxsize=128)
        self._recording_id: int | None = None
        self._recording_session_id: int | None = None
        self._profile_id: int | None = None
        self._stop_event = threading.Event()
        self._installing = False
        self._transcriber_available: bool | None = None
        self._transcription_process = None
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        self.state.add_listener(self.sync)
        self._watcher = threading.Thread(target=self._watch_loop, name="speech-watcher", daemon=True)
        self._watcher.start()

    def status(self) -> SpeechStatus:
        with self._lock:
            return SpeechStatus(self._status.code, self._status.text, self._status.progress)

    def _set_status(self, code: str, text: str, progress: int | None = None) -> None:
        with self._lock:
            self._status = SpeechStatus(code, text, progress)

    def enabled(self) -> bool:
        return (self.storage.get_setting("speech_recording_enabled") or "0") == "1"

    def set_enabled(self, enabled: bool) -> None:
        self.storage.set_setting("speech_recording_enabled", "1" if enabled else "0")
        self.sync()

    def device_index(self) -> int | None:
        value = (self.storage.get_setting("speech_device_index") or "").strip()
        return int(value) if value.lstrip("-").isdigit() else None

    def set_device_index(self, index: int | None) -> None:
        self.storage.set_setting("speech_device_index", "" if index is None else str(int(index)))
        self.sync(restart=True)

    def model_name(self) -> str:
        value = (self.storage.get_setting("speech_model") or "base").strip().lower()
        return value if value in {"tiny", "base", "small"} else "base"

    def delete_audio_after_transcription(self) -> bool:
        value = self.storage.get_setting("speech_delete_audio")
        return value != "0"

    def set_delete_audio_after_transcription(self, enabled: bool) -> None:
        self.storage.set_setting("speech_delete_audio", "1" if enabled else "0")

    def set_model_name(self, name: str) -> None:
        name = name.strip().lower()
        if name not in {"tiny", "base", "small"}:
            name = "base"
        self.storage.set_setting("speech_model", name)

    def available_devices(self) -> list[tuple[int, str]]:
        try:
            import sounddevice as sd
            result = []
            for idx, info in enumerate(sd.query_devices()):
                if int(info.get("max_input_channels", 0)) > 0:
                    result.append((idx, str(info.get("name") or f"Input {idx}")))
            return result
        except Exception:
            return []

    def has_transcriber(self, refresh: bool = False) -> bool:
        if getattr(sys, "frozen", False):
            # A separate executable is installed only if the streamer opts in.
            return component_installed()
        if self._transcriber_available is not None and not refresh:
            return self._transcriber_available
        try:
            import faster_whisper  # noqa: F401
            self._transcriber_available = True
        except Exception:
            self._transcriber_available = False
        return bool(self._transcriber_available)

    def installing(self) -> bool:
        with self._lock:
            return self._installing

    def install_transcriber(self) -> None:
        """Install the optional speech component from inside the source build.

        Release builds can bundle the component, so normal streamers will not need
        to browse the application folder or run a separate .bat file.
        """
        if self.has_transcriber():
            self._set_status("ready", "Анализ речи уже установлен")
            return
        with self._lock:
            if self._installing:
                return
            self._installing = True
        self._set_status("installing", "Устанавливаю анализ речи · это нужно сделать только один раз")

        def worker() -> None:
            try:
                if getattr(sys, "frozen", False):
                    install_component(lambda message: self._set_status("installing", message))
                    if not component_installed():
                        raise RuntimeError("Установка компонента речи не завершилась")
                    self._set_status("ready", "Анализ речи готов. Модель загрузится при первом использовании.")
                    return
                req = Path(__file__).resolve().parents[2] / "requirements-speech.txt"
                if not req.exists():
                    raise RuntimeError("Не найден файл компонента анализа речи")
                proc = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", str(req)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=1800,
                )
                if proc.returncode != 0:
                    tail = (proc.stderr or "").strip().splitlines()[-1:] or ["неизвестная ошибка"]
                    raise RuntimeError(tail[0])
                if not self.has_transcriber(refresh=True):
                    raise RuntimeError("Установка завершилась, но модуль не удалось загрузить")
                self._set_status("ready", "Анализ речи установлен · можно пользоваться без отдельного установщика")
            except Exception as exc:
                self._set_status("error", f"Не удалось установить анализ речи: {exc}")
            finally:
                with self._lock:
                    self._installing = False

        threading.Thread(target=worker, name="speech-ai-install", daemon=True).start()

    def _watch_loop(self) -> None:
        while True:
            try:
                self.sync()
            except Exception:
                pass
            time.sleep(1.5)

    def shutdown(self) -> None:
        self._stop_recording()
        proc = self._transcription_process
        if proc is not None:
            try:
                alive = proc.is_alive() if hasattr(proc, "is_alive") else proc.poll() is None
                if alive:
                    proc.terminate()
            except Exception:
                pass

    def sync(self, restart: bool = False) -> None:
        profile = self.state.profile
        session = self.storage.active_session(profile.id)
        should_record = bool(self.enabled() and session and session.paused_at is None)
        with self._lock:
            recording_session = self._recording_session_id
            recording_profile = self._profile_id
        if restart and recording_session is not None:
            self._stop_recording()
            recording_session = None
        if should_record:
            if recording_session != session.id or recording_profile != profile.id:
                self._stop_recording()
                self._start_recording(profile.id, session.id)
        else:
            self._stop_recording()
            proc = self._transcription_process
            transcribing = proc is not None and (proc.is_alive() if hasattr(proc, "is_alive") else proc.poll() is None)
            if transcribing or self.installing():
                return  # Don't overwrite download/transcription progress during idle refresh.
            if self.enabled():
                # Don't overwrite the actual worker result every 1.5 seconds.
                if self.status().code not in {"done", "error", "ready"}:
                    self._set_status("armed", "Микрофон готов · запись начнётся вместе с активной сессией")
            else:
                # Keep the final recognition result visible until the next action.
                if self.status().code not in {"done", "error", "ready"}:
                    self._set_status("idle", "Анализ речи выключен")

    def _start_recording(self, profile_id: int, session_id: int) -> None:
        try:
            import sounddevice as sd
        except Exception:
            self._set_status("error", "Не удалось загрузить микрофонный модуль")
            return
        stamp = time.strftime("%Y%m%d_%H%M%S")
        path = RECORDINGS_DIR / f"profile_{profile_id}_session_{session_id}_{stamp}.wav"
        started_at = time.time()
        recording_id = self.storage.create_speech_recording(profile_id, session_id, str(path), started_at)
        self._queue = queue.Queue(maxsize=128)
        self._stop_event.clear()

        def callback(indata, frames, time_info, status):
            try:
                self._queue.put_nowait(bytes(indata))
            except queue.Full:
                pass

        device = self.device_index()
        try:
            stream = sd.RawInputStream(
                samplerate=16000,
                channels=1,
                dtype="int16",
                blocksize=1600,
                device=device,
                callback=callback,
            )
            stream.start()
        except Exception as exc:
            self.storage.finish_speech_recording(recording_id, time.time(), "error")
            self._set_status("error", f"Не удалось открыть микрофон: {exc}")
            return

        def writer() -> None:
            try:
                with wave.open(str(path), "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(16000)
                    while not self._stop_event.is_set() or not self._queue.empty():
                        try:
                            chunk = self._queue.get(timeout=0.25)
                        except queue.Empty:
                            continue
                        if chunk is None:
                            break
                        wav.writeframes(chunk)
            finally:
                self.storage.finish_speech_recording(recording_id, time.time(), "recorded")

        self._stream = stream
        self._recording_id = recording_id
        self._recording_session_id = session_id
        self._profile_id = profile_id
        self._writer_thread = threading.Thread(target=writer, name=f"speech-writer-{session_id}", daemon=True)
        self._writer_thread.start()
        self._set_status("recording", "Записываю микрофон для анализа после стрима")

    def _stop_recording(self) -> None:
        with self._lock:
            stream = self._stream
            writer = self._writer_thread
            if stream is None and self._recording_session_id is None:
                return
            self._stream = None
            self._writer_thread = None
            self._recording_session_id = None
            self._profile_id = None
            self._stop_event.set()
        try:
            if stream is not None:
                stream.stop()
                stream.close()
        except Exception:
            pass
        try:
            self._queue.put_nowait(None)
        except Exception:
            pass
        if writer and writer.is_alive():
            writer.join(timeout=2)

    def recording_summary(self, profile_id: int, session_id: int | None) -> str:
        """User-friendly recording check without needing a running speech model."""
        if session_id is None:
            return "Выбери сессию, чтобы проверить, сохранился ли звук."
        rows = self.storage.list_speech_recordings(profile_id, session_id=int(session_id))
        if not rows:
            return "Для этой сессии нет записи голоса. Включи запись ДО запуска новой сессии."
        found = 0
        seconds = 0.0
        total_bytes = 0
        for item in rows:
            audio = Path(str(item.get("path") or ""))
            if audio.is_file():
                found += 1
                total_bytes += audio.stat().st_size
                try:
                    with wave.open(str(audio), "rb") as wav:
                        seconds += wav.getnframes() / max(1, wav.getframerate())
                except (wave.Error, OSError):
                    pass
        if found:
            return f"Запись найдена: {found} файл(ов), около {int(seconds)} сек., {total_bytes / 1024 / 1024:.1f} МБ."
        if all(str(r.get("status")) == "transcribed" for r in rows):
            return "Запись уже распознана и удалена по настройке. Результат ищи выше в «Речь стримера»."
        return "Запись сессии недоступна. Проверь микрофон и настройку сохранения голоса."

    def transcribe_session(self, profile_id: int, session_id: int) -> None:
        if not self.has_transcriber():
            raise RuntimeError("Сначала нажмите «Установить анализ речи» в этом разделе.")
        proc = self._transcription_process
        if proc is not None:
            alive = proc.is_alive() if hasattr(proc, "is_alive") else proc.poll() is None
            if alive:
                raise RuntimeError("Распознавание другой сессии уже выполняется")
        recordings = self.storage.list_speech_recordings(profile_id, session_id=session_id)
        pending = [r for r in recordings if r["status"] in {"recorded", "error"} and Path(r["path"]).exists()]
        if not pending:
            raise RuntimeError(self.recording_summary(profile_id, session_id) + " Нечего распознавать повторно.")

        if getattr(sys, "frozen", False):
            self._transcribe_frozen(int(profile_id), int(session_id), pending)
            return

        ctx = mp.get_context("spawn")
        progress = ctx.Queue()
        proc = ctx.Process(
            target=_transcribe_process,
            args=(str(self.storage.path), int(profile_id), int(session_id), pending, self.model_name(), self.delete_audio_after_transcription(), progress),
            name=f"speech-transcribe-{session_id}",
            daemon=True,
        )
        self._transcription_process = proc
        self._set_status("transcribing", f"Подготавливаю распознавание · записей: {len(pending)}", 0)
        proc.start()

        def monitor() -> None:
            final_seen = False
            while proc.is_alive() or not progress.empty():
                try:
                    code, text = progress.get(timeout=0.4)
                    self._set_status(code, text)
                    if code in {"done", "error"}:
                        final_seen = True
                except queue.Empty:
                    pass
                except Exception:
                    break
            proc.join(timeout=1)
            if not final_seen:
                if proc.exitcode == 0:
                    self._set_status("done", "Распознавание завершено · текст добавлен в Анализ")
                else:
                    self._set_status("error", "Распознавание завершилось с ошибкой")
            self._transcription_process = None

        threading.Thread(target=monitor, name=f"speech-monitor-{session_id}", daemon=True).start()

    def _transcribe_frozen(self, profile_id: int, session_id: int, pending: list[dict]) -> None:
        """Run the optional speech EXE outside of the main GUI process."""
        executable = worker_path()
        if not component_installed() or not executable.is_file():
            raise RuntimeError("Сначала установите анализ речи в приложении")
        job_dir = DATA_DIR / "speech_jobs"
        job_dir.mkdir(parents=True, exist_ok=True)
        # Job files contain only local recording paths and session identifiers.
        fd, path = tempfile.mkstemp(prefix="job-", suffix=".json", dir=str(job_dir))
        job_path = Path(path)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fp:
                json.dump({
                    "db_path": str(self.storage.path),
                    "profile_id": profile_id,
                    "session_id": session_id,
                    "recordings": pending,
                    "model": self.model_name(),
                    "delete_audio": self.delete_audio_after_transcription(),
                }, fp, ensure_ascii=False)
        except Exception:
            job_path.unlink(missing_ok=True)
            raise
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            proc = subprocess.Popen(
                [str(executable), "--job", str(job_path)],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding="utf-8", errors="replace",
                creationflags=flags,
            )
        except Exception:
            job_path.unlink(missing_ok=True)
            raise
        self._transcription_process = proc
        self._set_status("transcribing", f"Подготавливаю распознавание · записей: {len(pending)}", 0)

        def monitor() -> None:
            final_seen = False
            try:
                assert proc.stdout is not None
                for line in proc.stdout:
                    try:
                        event = json.loads(line)
                        code = str(event.get("code") or "progress")
                        message = str(event.get("text") or "")
                        self._set_status(code, message, event.get("progress"))
                        if code in {"done", "error"}:
                            final_seen = True
                    except (ValueError, AttributeError):
                        continue
                return_code = proc.wait()
                if not final_seen:
                    self._set_status(
                        "error",
                        f"Не удалось получить результат распознавания (код {return_code}). Попробуй ещё раз.",
                    )
            finally:
                job_path.unlink(missing_ok=True)
                self._transcription_process = None

        threading.Thread(target=monitor, name="speech-exe-monitor", daemon=True).start()
