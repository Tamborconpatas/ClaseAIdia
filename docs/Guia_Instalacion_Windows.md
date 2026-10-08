# Guía de Instalación en Windows (Desde Cero) — ClaseAIdia

Esta guía documenta la instalación paso a paso de **ClaseAIdia** (Universal Local Transcriber) en un sistema Windows recién instalado ("desde cero"), utilizando **Conda** como gestor de entornos y detallando las restricciones críticas de versión de Python. Verificada de punta a punta en Windows 11 con GPU NVIDIA (RTX 2050) el 2026-09-04 — ver `QA.md` para el detalle de qué se probó.

> **Conda no es obligatorio.** Esta guía lo usa porque es cómodo para fijar la versión de Python, pero el camino con `venv` (incluido en cualquier instalación normal de Python, sin instalar nada extra) está en el [`README.md`](../README.md#2-configuración-del-entorno-python) — verificado igual de funcional en Windows el 2026-09-05 (instalación de Python 3.12 sin admin vía `winget`, `pip install -r requirements.txt` completo, 43/43 tests, app levantando y respondiendo). Usa esta guía solo si ya tienes o prefieres Conda.

---

## 1. Versión de Python: 3.12 o superior

> [!NOTE]
> **Usa Python 3.12 o superior.** Probado en 3.12 y 3.14. Versiones anteriores no sirven: `numpy`, `scipy` y `librosa` exigen 3.12 como mínimo.

---

## 2. Configuración del Entorno con Conda

Para evitar cualquier conflicto con versiones globales de Python que traiga Windows o la tienda de aplicaciones, se debe aislar el proyecto mediante un entorno Conda con Python 3.12 o superior (los ejemplos usan 3.14).

### Paso 2.1: Abrir la terminal
Abre **PowerShell** o **Terminal de Windows** (puedes usar la terminal integrada de tu editor o Anaconda / Miniconda Prompt).

### Paso 2.2: Crear el entorno virtual con Python 3.14
```powershell
conda create -n transcriptor-env python=3.14 -y
```

*(Nota: Si usas una instalación limpia de Miniconda y te solicita aceptar los términos de los canales oficiales, ejecuta:)*
```powershell
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/msys2
```

### Paso 2.3: Activar el entorno
```powershell
conda activate transcriptor-env
```
Verifica que el intérprete activo sea 3.12 o superior:
```powershell
python --version
# Debe responder: Python 3.12.x o superior (por ejemplo 3.14.x)
```

---

## 3. Requisito del Sistema: FFMPEG

La aplicación requiere **FFmpeg** para convertir y normalizar los audios de clases a 16 kHz Mono en disco (ahorrando gigabytes de memoria RAM).

1. Comprueba si ya está disponible en tu terminal:
   ```powershell
   ffmpeg -version
   ```
2. Si no está instalado, instálalo fácilmente con el gestor de paquetes de Windows:
   ```powershell
   winget install Gyan.FFmpeg
   ```
   *(Reinicia la terminal de PowerShell tras la instalación para que reconozca la nueva variable de entorno PATH).*

---

## 4. Instalación de PyTorch (Aceleración de IA)

Para evitar que `pip` descargue paquetes CUDA innecesarios o versiones incompatibles, instala PyTorch indicando explícitamente el índice correspondiente a tu hardware:

### Caso A: PC con GPU NVIDIA (Recomendado para equipos con GeForce / RTX)
Si tu equipo cuenta con una tarjeta NVIDIA (por ejemplo, RTX 2050, 3060, 4060, etc.):
```powershell
pip install torch==2.14.1 torchaudio==2.11.0 --index-url https://download.pytorch.org/whl/cu126
```

### Caso B: PC sin GPU dedicada (Solo CPU)
Para computadores de colegios o notebooks estándar sin tarjeta de video:
```powershell
pip install torch==2.14.1 torchaudio==2.11.0 --index-url https://download.pytorch.org/whl/cpu
```

---

## 5. Instalación de Dependencias del Proyecto

Con PyTorch ya configurado, instala las librerías del proyecto desde la raíz de la carpeta `ClaseAIdia`:

```powershell
pip install -r requirements.txt
```

*(Nota: `deepfilternet` no se incluye en este archivo para evitar exigir compiladores de Rust durante la instalación base. La limpieza de ruido por defecto usa filtros Wiener DSP de `scipy` y `noisereduce`, completamente funcionales).*

---

## 6. Validación de la Instalación

### 6.1. Ejecución de Pruebas Automatizadas
Ejecuta la suite de pruebas con `pytest` para certificar la integridad de los modelos de base de datos, validadores y endpoints:
```powershell
python -m pytest tests/ -v
```
*(Debes obtener 43 tests superados exitosamente).*

### 6.2. Verificación de Detección de Hardware
Comprueba qué motor y hardware utilizará la aplicación:
```powershell
python -c "from infraestructura.hardware import detect_gpu_vendor; print('Hardware detectado:', detect_gpu_vendor())"
```
- Debe imprimir `nvidia` si tienes tarjeta NVIDIA configurada con CUDA, o `none` si operará en CPU.

### 6.3. Levantar la Aplicación
Inicia el servidor y la interfaz juntos con un doble clic en `iniciar.bat` (o `iniciar.bat demo` para probar con datos de ejemplo). Se abre el navegador en `http://localhost:5173`; para detener todo, Ctrl+C o cierra la ventana.

---

## 7. Ruta hacia el Ejecutable Portable (pendiente — Fase 6)

De acuerdo a la arquitectura del proyecto (`CLAUDE.md` y `docs/fases/fase-6-despliegue-acceso-remoto.md`), el objetivo final de despliegue para colegios es una **instalación portable sin instalador y sin permisos de administrador**, empaquetada con PyInstaller.

**Estado real: es trabajo pendiente de la Fase 6**, que va después de Frontend (Fase 3) y Control de Clase en Vivo (Fase 4). No hay que construir esto todavía; queda anotado para cuando corresponda:

- **Modo Carpeta Portable (`--onedir`), no `--onefile`**: PyTorch, CUDA y los modelos de IA ocupan más de 2.5 GB en librerías nativas. Un solo ejecutable (`--onefile`) tardaría minutos en cada arranque descomprimiendo esos gigabytes a `%TEMP%`; la carpeta distribuible arranca al instante.
- El script de build deberá copiar `ffmpeg.exe` junto al ejecutable (para no depender del PATH del sistema en un PC de sala que nunca tuvo FFmpeg instalado) — el código fuente (`infraestructura/herramientas_ffmpeg.py`) hoy solo busca `ffmpeg` en el PATH.
