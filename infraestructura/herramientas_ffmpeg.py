import os


def optimize_audio_ffmpeg(input_path: str) -> str:
    """
    [OPTIMIZACIÓN RAM EXTREMA]
    Convierte el audio a 16kHz Mono vía ffmpeg (disk-to-disk) ANTES de cargarlo en Python.
    Evita que arreglos gigantes (ej. audios estéreo a 48kHz de 2+ horas) destruyan la RAM del sistema.
    Devuelve la ruta al archivo .wav optimizado.
    """
    import subprocess
    import tempfile
    import shutil

    if not shutil.which("ffmpeg"):
        print("⚠️ ADVERTENCIA: 'ffmpeg' no encontrado en el sistema. Peligro de OOM RAM en archivos largos.")
        return input_path

    fname = os.path.basename(input_path)
    base, _ = os.path.splitext(fname)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.wav', prefix=f"opt_{base[:15]}_")
    output_path = tmp.name
    tmp.close()

    try:
        print(f"[Sistema] Minimizando rastro RAM vía FFmpeg (16kHz Mono) para: '{fname}'...")
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
            "-loglevel", "error",
            output_path
        ]
        subprocess.run(cmd, check=True)
        return output_path
    except Exception as e:
        print(f"⚠️ Error al optimizar con FFmpeg: {e}")
        if os.path.exists(output_path):
            os.remove(output_path)
        return input_path
