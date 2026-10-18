Donathon Timer 0.9.4 Beta 5 — HOTFIX распознавания речи

ПРИЧИНА: faster-whisper 1.2.1 передает metadata_errors в av.open(), а PyAV 19 этот аргумент удалил.
Исправление: av==17.1.0 в requirements-speech.txt, плюс buildtools/verify_speech_stack.py, который проверяет
декодирование WAV реальными библиотеками при GitHub Actions сборке до публикации релиза.

КАК ОБНОВИТЬ:
1. Закрой Donathon Timer.
2. Распакуй Beta5_Update.zip отдельно.
3. Скопируй все его файлы/папки в локальный DonathonTimer-GitHub, соглашаясь на замену. НЕ трогай .git.
4. GitHub Desktop: Commit to main, затем Push origin.
5. GitHub Actions -> Build and publish Windows beta -> Run workflow, tag v0.9.4-beta5.
6. После зеленой сборки скачай Setup.exe из GitHub Releases и установи поверх Beta4.
7. Запусти приложение, раздел Анализ: новый модуль речи имеет иной хеш и потребует установить его снова.
8. Нажми «Установить анализ речи», дождись завершения и затем повтори распознавание старой записи.

Не удаляй %LOCALAPPDATA%\DonathonTimer — там твои записи и база.
Если сборка GitHub красная, пришли текст ошибки из Actions. На Windows полноценный EXE здесь не запускался.
