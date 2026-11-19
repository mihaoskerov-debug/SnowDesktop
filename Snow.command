#!/bin/bash
# Запуск снега на macOS двойным кликом. Python 3.9+ должен быть установлен (python.org или Homebrew).
cd "$(dirname "$0")"
PY="$(command -v python3)"
if [ -z "$PY" ]; then
  osascript -e 'display dialog "Не найден python3. Установи Python с python.org и запусти снова." buttons {"OK"}'
  exit 1
fi
nohup "$PY" snow.pyw >/dev/null 2>&1 &
disown
exit 0
