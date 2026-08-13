@echo off
cd /d "%~dp0"
if exist "DiskCleaner.exe" (
    start "" "DiskCleaner.exe"
    exit /b 0
)
where pythonw >nul 2>nul
if not errorlevel 1 (
    start "" pythonw "disk_cleaner.py"
    exit /b 0
)
echo [Error] Neither DiskCleaner.exe nor Python was found.
pause
