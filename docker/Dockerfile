# Backend de ClaseAIdia (FastAPI + trabajador de procesamiento). La interfaz va en docker/Dockerfile.web.
FROM python:3.14-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Por defecto solo CPU: el servidor del colegio no depende de GPU. Los archivos docker-compose.gpu-*.yml
# cambian estos argumentos. CTranslate2 (motor de faster-whisper) está compilado contra CUDA 12
# (libcublas.so.12): el índice genérico de pip resuelve a CUDA 13 (incompatible), por eso la variante
# NVIDIA se fija a cu126. torch y torchaudio van juntos: si quedan de índices distintos, torchaudio no
# encuentra las librerías CUDA que espera.
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
ARG TORCH_VERSION=2.14.1
ARG TORCHAUDIO_VERSION=2.11.0

COPY requirements.txt .
RUN pip install --no-cache-dir torch==${TORCH_VERSION} torchaudio==${TORCHAUDIO_VERSION} --index-url ${TORCH_INDEX}
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# El contenedor corre con el UID del anfitrión (sin entrada en /etc/passwd): HOME y las cachés van a /data.
ENV HOME=/data \
    HF_HOME=/data/hf \
    NUMBA_CACHE_DIR=/tmp/numba \
    PYTHONUTF8=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# Pone la base al día (alembic) y levanta la API. Sin --reload ni access log: es el servidor 24/7.
CMD ["sh", "-c", "python -m alembic upgrade head && exec python -m uvicorn api:app --host 0.0.0.0 --port 8000 --no-access-log"]
