"""Optional standalone speech engine for frozen Windows builds.

Downloaded only after explicit opt-in, hash-checked against the manifest embedded
at build time and extracted into per-user LOCALAPPDATA (never the install folder).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from .config import DATA_DIR

COMPONENT_DIR = DATA_DIR / "components" / "speech"
MANIFEST = Path(__file__).resolve().parent / "assets" / "speech_release.json"
EXE_NAME = "DonathonSpeechWorker.exe"
MAX_ARCHIVE_BYTES = 900 * 1024 * 1024
MAX_UNPACKED_BYTES = 2 * 1024 * 1024 * 1024


def read_manifest() -> dict:
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError("В этой сборке не указана загрузка модуля речи") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Повреждены данные о модуле речи")
    return data


def worker_path() -> Path:
    return COMPONENT_DIR / "DonathonSpeechWorker" / EXE_NAME


def component_installed() -> bool:
    exe = worker_path()
    if not exe.is_file():
        return False
    try:
        manifest = read_manifest()
        installed = json.loads((COMPONENT_DIR / "installed.json").read_text(encoding="utf-8"))
        return installed.get("sha256") == manifest.get("sha256") and bool(manifest.get("sha256"))
    except (OSError, ValueError, RuntimeError):
        return False


def install_component(progress: Callable[[str], None]) -> None:
    """Download/extract with a hash check and safe member paths, then publish atomically."""
    manifest = read_manifest()
    url = str(manifest.get("url") or "")
    expected_hash = str(manifest.get("sha256") or "").lower()
    if not url.startswith("https://github.com/") or "/releases/download/" not in url:
        raise RuntimeError("Компонент речи пока не опубликован. Установите официальную beta-сборку из Releases.")
    if len(expected_hash) != 64 or any(c not in "0123456789abcdef" for c in expected_hash):
        raise RuntimeError("Не указан контрольный хеш модуля речи")
    if component_installed():
        progress("Компонент речи уже установлен")
        return

    COMPONENT_DIR.parent.mkdir(parents=True, exist_ok=True)
    tmp_root = Path(tempfile.mkdtemp(prefix="speech-install-", dir=str(COMPONENT_DIR.parent)))
    archive = tmp_root / "component.zip"
    unpack = tmp_root / "unpacked"
    unpack.mkdir()
    try:
        progress("Загружаю анализ речи…")
        req = urllib.request.Request(url, headers={"User-Agent": "DonathonTimer-Beta/0.9.4"})
        with urllib.request.urlopen(req, timeout=60) as response, archive.open("wb") as output:
            content_length = int(response.headers.get("Content-Length") or 0)
            if content_length > MAX_ARCHIVE_BYTES:
                raise RuntimeError("Архив компонента слишком большой")
            hasher = hashlib.sha256()
            received = 0
            reported = -1
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                received += len(chunk)
                if received > MAX_ARCHIVE_BYTES:
                    raise RuntimeError("Загрузка превысила разрешённый размер")
                hasher.update(chunk)
                output.write(chunk)
                if content_length:
                    percent = min(100, int(100 * received / content_length))
                    if percent // 5 != reported:
                        reported = percent // 5
                        progress(f"Загружаю анализ речи · {percent}%")
        if hasher.hexdigest() != expected_hash:
            raise RuntimeError("Контрольная сумма загрузки не совпала. Компонент не установлен.")

        progress("Проверяю и распаковываю компонент…")
        with zipfile.ZipFile(archive) as zf:
            total = 0
            for member in zf.infolist():
                name = member.filename.replace("\\", "/")
                parts = Path(name).parts
                if not parts or name.startswith("/") or ".." in parts or ":" in name or len(name) > 512:
                    raise RuntimeError("Небезопасный файл в архиве компонента")
                total += member.file_size
                if total > MAX_UNPACKED_BYTES:
                    raise RuntimeError("Размер распакованного компонента слишком велик")
                # Do not create links or special files from an untrusted ZIP.
                mode = (member.external_attr >> 16) & 0o170000
                if mode not in {0, 0o100000, 0o040000}:
                    raise RuntimeError("Недопустимый тип файла компонента")
            zf.extractall(unpack)

        exe = unpack / "DonathonSpeechWorker" / EXE_NAME
        if not exe.is_file():
            raise RuntimeError("Архив не содержит исполняемый модуль речи")
        backup = COMPONENT_DIR.with_name("speech-backup")
        if backup.exists():
            shutil.rmtree(backup)
        if COMPONENT_DIR.exists():
            COMPONENT_DIR.rename(backup)
        try:
            unpack.rename(COMPONENT_DIR)
        except Exception:
            if backup.exists() and not COMPONENT_DIR.exists():
                backup.rename(COMPONENT_DIR)
            raise
        (COMPONENT_DIR / "installed.json").write_text(json.dumps({"sha256": expected_hash, "version": manifest.get("version")}, indent=2), encoding="utf-8")
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
        progress("Анализ речи установлен. Модель загрузится при первом распознавании.")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
