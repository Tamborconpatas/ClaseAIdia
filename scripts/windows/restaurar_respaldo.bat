@echo off
rem Restaura la base de datos desde el ultimo respaldo (o desde el archivo que arrastres sobre este .bat).
rem Antes hay que apagar el servidor: scripts\windows\quitar_servidor.bat. Despues, volver a iniciarlo con instalar_servidor.bat.
cd /d "%~dp0..\.."
set PYTHONUTF8=1
if exist "transcriptor-env\Scripts\python.exe" (set PY=transcriptor-env\Scripts\python.exe) else (set PY=python)
"%PY%" -m scripts.restaurar_respaldo %*
if errorlevel 1 goto fin
choice /c SN /m "Restaurar ahora"
if errorlevel 2 goto fin
"%PY%" -m scripts.restaurar_respaldo %* --si
:fin
pause
