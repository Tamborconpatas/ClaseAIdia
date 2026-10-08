#!/usr/bin/env bash
# Inicia ClaseAIdia completo (servidor + interfaz) y abre el navegador.
#   ./iniciar.sh           uso normal
#   ./iniciar.sh celular   https en la red del colegio, para grabar con el celular
#   ./iniciar.sh demo      con datos de ejemplo (no toca la base real)
cd "$(dirname "$0")" || exit 1
if [ -x transcriptor-env/bin/python ]; then PY=transcriptor-env/bin/python; else PY=python3; fi
export PYTHONUTF8=1
exec "$PY" -m scripts.iniciar "$@"
