@echo off
rem Prueba el servidor (con reinicio automatico) en una ventana. Cierrala para detenerlo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0servidor.ps1"
