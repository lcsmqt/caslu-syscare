@echo off
REM Atalho duplo-clique: prepara .venv e dependencias
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup-dev.ps1"
pause
