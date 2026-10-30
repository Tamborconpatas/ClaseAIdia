@echo off
rem Instala el inicio automatico del servidor (doble clic). No pide administrador.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1"
pause
