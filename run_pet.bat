@echo off
chcp 65001 >nul
echo Starting deskpet...
if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "%~dp0main.py"
) else (
    py -3 "%~dp0main.py"
)
if errorlevel 1 pause
