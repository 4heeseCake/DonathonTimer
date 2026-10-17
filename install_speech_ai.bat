@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Сначала один раз запусти run.bat, чтобы создать окружение программы.
  pause
  exit /b 1
)
echo Устанавливаю необязательный AI-модуль для распознавания речи...
.venv\Scripts\python.exe -m pip install -r requirements-speech.txt
if errorlevel 1 (
  echo.
  echo Установка завершилась с ошибкой.
  pause
  exit /b 1
)
echo.
echo Готово. Перезапусти Donathon Timer. При первом распознавании выбранная модель Whisper будет загружена автоматически.
pause
