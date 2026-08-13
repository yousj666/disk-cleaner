@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PYW="
for /f "delims=" %%i in ('where pythonw 2^>nul') do if not defined PYW set "PYW=%%i"

if defined PYW (
    start "" "%PYW%" "disk_cleaner.py"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo [错误] 未找到 Python，请先安装 Python 3。
        pause
        exit /b 1
    )
    python "disk_cleaner.py"
)
