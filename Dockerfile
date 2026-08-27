FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
# CTranslate2 (motor de faster-whisper) está compilado contra CUDA 12
# (libcublas.so.12) — el índice genérico de pip resuelve a CUDA 13
# (libcublas.so.13, incompatible), así que se fija a cu126 (misma versión
# de PyTorch más reciente, solo cambia la familia de CUDA con la que se
# compiló). torch y torchaudio van juntos: si quedan de índices distintos,
# torchaudio no encuentra las librerías CUDA que espera.
RUN pip install --no-cache-dir torch==2.13.0 torchaudio==2.11.0 --index-url https://download.pytorch.org/whl/cu126
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 7862

CMD ["python", "app.py"]
