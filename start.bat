@echo off
chcp 65001 >nul
title Kitob bot
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python не найден. Установите Python 3.11+ с https://www.python.org/downloads/
  echo При установке отметьте галочку "Add python.exe to PATH".
  pause
  exit /b 1
)

if not exist ".venv" (
  echo Создаю окружение...
  python -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
pip install -r bot\requirements.txt

if not exist ".env" (
  echo Файл .env не найден. Скопируйте .env.example в .env и впишите BOT_TOKEN.
  pause
  exit /b 1
)

echo.
echo Бот запускается. Не закрывайте это окно — пока оно открыто, бот работает.
echo Остановить: Ctrl+C
echo.
python bot\main.py
pause
