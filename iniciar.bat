@echo off
rem Inicia ClaseAIdia completo (servidor + interfaz) y abre el navegador. Doble clic.
rem   iniciar.bat           uso normal
rem   iniciar.bat celular   https en la red del colegio, para grabar con el celular
rem   iniciar.bat demo      con datos de ejemplo (no toca la base real)
cd /d "%~dp0"
title ClaseAIdia
if exist "transcriptor-env\Scripts\python.exe" (set PY=transcriptor-env\Scripts\python.exe) else (set PY=python)
set PYTHONUTF8=1
"%PY%" -m scripts.iniciar %*
echo.
pause
