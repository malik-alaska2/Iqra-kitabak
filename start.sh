#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

command -v python3 >/dev/null || { echo "Установите Python 3.11+"; exit 1; }
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r bot/requirements.txt
[ -f .env ] || { echo "Нет файла .env"; exit 1; }

echo "Бот запускается. Остановить: Ctrl+C"
python bot/main.py
