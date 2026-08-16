@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo Python не найден. Установите Python 3.10+ с https://www.python.org/
    pause
    exit /b 1
)

python -c "import yt_dlp" 2>nul
if errorlevel 1 (
    echo Установка зависимостей...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Не удалось установить yt-dlp.
        pause
        exit /b 1
    )
)

if "%~1"=="" (
    python download.py
) else (
    python download.py %*
)

if errorlevel 1 pause
