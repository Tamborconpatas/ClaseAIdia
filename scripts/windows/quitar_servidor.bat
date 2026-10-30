@echo off
rem Desinstala el inicio automatico y detiene el servidor.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1" -Quitar
pause
