@echo off
rem Prueba de humo de la instalacion: procesa una clase de mentira de punta a punta en una carpeta temporal.
rem No toca la base de datos ni las carpetas del colegio. Se puede correr con el servidor encendido o apagado.
rem Con una voz de verdad (para probar tambien Ollama):  probar_instalacion.bat --audio ruta\clase.wav
cd /d "%~dp0..\.."
if exist "transcriptor-env\Scripts\python.exe" (set PY=transcriptor-env\Scripts\python.exe) else (set PY=python)
"%PY%" -m scripts.prueba_de_humo %*
pause
