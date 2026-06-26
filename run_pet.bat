@echo off
chcp 65001 >nul
echo Starting deskpet...
"C:\Program Files\Python312\python.exe" "%~dp0main.py"
if errorlevel 1 pause
