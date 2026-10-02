"""
mejorador_audio.py — Pipeline de Mejora de Audio Avanzado
=========================================================
Pre-procesa audio antes de la transcripción para mejorar la claridad de voz.
Diseñado para grabaciones escolares: voz opacada, ruido ambiental, niveles variables.

Modos de reducción de ruido:
  'none'      : Sin reducción de ruido
  'light_dsp' : DSP ligero — solo sustracción suave (bueno para ruido leve)
  'dsp'       : Wiener filter estándar (noisereduce) — modo equilibrado
  'heavy_dsp' : Wiener filter agresivo — entornos muy ruidosos
  'mmse'      : MMSE espectral PyTorch — sin deps externas, muy buena calidad
  'deepfilter': DeepFilterNet IA — máxima calidad, primera vez descarga ~30MB

Capas de procesamiento (cada una independiente):
  - Normalización RMS de entrada
  - Filtro pasa-altos (quita rumble: AC, fans, impactos)
  - Filtro pasa-bajos (quita sibilancias extremas)
  - Reducción de ruido (modo seleccionable)
  - Realce de voz (enfatiza 1kHz-4kHz, zona de inteligibilidad)
  - Compresión dinámica (acerca volúmenes bajos y altos)
  - Normalización de pico final
"""

import os
import tempfile
import numpy as np
import soundfile as sf

# ─── Imports opcionales ────────────────────────────────────────────────────────

try:
    import noisereduce as nr
    HAS_NOISEREDUCE = True
except ImportError:
    HAS_NOISEREDUCE = False

try:
    from df.enhance import enhance, init_df
    HAS_DEEPFILTER = True
except (ImportError, ModuleNotFoundError):
    HAS_DEEPFILTER = False

try:
    from scipy.signal import butter, sosfilt, sosfiltfilt
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


# ─── Clase principal ───────────────────────────────────────────────────────────

def perfil_de_ruido(audio: np.ndarray, sr: int, segundos: float) -> np.ndarray:
    """El tramo con ruido de fondo y sin voz, que es lo que el filtro aprende a quitar.

    Antes eran los primeros segundos del audio, pero en una clase el profesor suele estar hablando desde el inicio:
    el filtro aprendía su voz como si fuera ruido y la borraba (medido: con `dsp` se perdían 38 s de habla de cada
    4 minutos). Ahora se toma una de las ventanas más silenciosas del audio completo (percentil 5, ignorando el
    silencio digital exacto, que no dice nada de la sala)."""
    n = int(sr * segundos)
    if len(audio) <= n:
        return audio
    ventanas = len(audio) // n
    rms = np.sqrt(np.mean(audio[: ventanas * n].reshape(ventanas, n) ** 2, axis=1))
    con_senal = np.flatnonzero(rms > 1e-4)
    if len(con_senal) == 0:
        return audio[:n]
    elegida = con_senal[np.argsort(rms[con_senal])[len(con_senal) // 20]]
    return audio[elegida * n:(elegida + 1) * n]


TRAMO_S = 300  # segundos de audio que se limpian de una vez
TRASLAPE_S = 2  # segundos que se superponen entre un tramo y el siguiente, con fundido, para que no se note el empalme


def por_tramos(funcion, audio: np.ndarray, sr: int, tramo_s: float = TRAMO_S, traslape_s: float = TRASLAPE_S) -> np.ndarray:
    """Aplica `funcion` (que devuelve un audio del mismo largo) por tramos de `tramo_s` segundos en vez de al archivo
    entero, así la memoria que usa no depende de cuánto dura la clase. Los tramos se superponen `traslape_s` segundos
    y se unen con un fundido lineal (las dos rampas suman 1: el audio sin procesar vuelve idéntico)."""
    n, tramo, traslape = len(audio), int(tramo_s * sr), int(traslape_s * sr)
    if n <= tramo + traslape:
        return funcion(audio)
    rampa = np.linspace(0, 1, traslape + 2, dtype=np.float32)[1:-1]
    salida = np.zeros(n, dtype=np.float32)
    inicio = 0
    while True:
        fin = min(n, inicio + tramo + traslape)
        procesado = np.asarray(funcion(audio[inicio:fin]), dtype=np.float32)
        largo = fin - inicio
        if len(procesado) != largo:  # por si el filtro devuelve unas muestras de más o de menos
            procesado = np.pad(procesado[:largo], (0, max(0, largo - len(procesado))))
        peso = np.ones(largo, dtype=np.float32)
        if inicio > 0:
            peso[:traslape] = rampa
        if fin < n:
            peso[-traslape:] = 1 - rampa
        salida[inicio:fin] += procesado * peso
        if fin >= n:
            return salida
        inicio = fin - traslape


def _rms(audio: np.ndarray) -> float:
    """Valor RMS sin crear una copia del audio al cuadrado (con una clase larga son cientos de MB)."""
    total = 0.0
    paso = 1 << 22
    for i in range(0, len(audio), paso):
        trozo = audio[i:i + paso].astype(np.float64)
        total += float(np.dot(trozo, trozo))
    return float(np.sqrt(total / max(len(audio), 1)))


class AudioEnhancer:
    """Pipeline de mejora de audio multi-capa con configuración granular."""

    MODES = {
        'none':        "Sin reducción de ruido",
        'light_dsp':   "Ligero DSP (ruido leve)",
        'dsp':         "DSP estándar (Wiener - equilibrado)",
        'heavy_dsp':   "DSP agresivo (ruido intenso)",
        'mmse':        "MMSE espectral PyTorch (alta calidad, sin deps)",
        'deepfilter':  "DeepFilterNet IA (máxima calidad)",
    }

    def __init__(self):
        self._df_model = None
        self._df_state = None

    # ── Carga lazy DeepFilterNet ──────────────────────────────────────────────

    def _load_df_model(self):
        if not HAS_DEEPFILTER:
            raise ImportError("DeepFilterNet no disponible. pip install deepfilternet")
        if self._df_model is None:
            import torch
            import sys
            import df.enhance

            print("[AudioEnhancer] Iniciando DeepFilterNet en modo aislado (CPU)...")
            
            # --- PARCHE GLOBAL ---
            # 1. Engañamos a torch para que crea que no hay CUDA durante init_df
            orig_is_available = torch.cuda.is_available
            torch.cuda.is_available = lambda: False
            
            try:
                self._df_model, self._df_state, _ = init_df()
                # 2. Asegurar que el modelo esté en CPU
                self._df_model = self._df_model.cpu()
                
                # 3. Nuclear Monkey-patch: forzar get_device a CPU en TODOS los modulos de df
                # que ya hayan sido importados (esto rompe el binding local de 'from .utils import get_device')
                def force_cpu(): return torch.device('cpu')
                
                for mod_name, mod in sys.modules.items():
                    if mod_name == "df" or mod_name.startswith("df."):
                        if hasattr(mod, "get_device"):
                            mod.get_device = force_cpu

            finally:
                # Restaurar torch para que el resto de la app (NeMo) use GPU
                torch.cuda.is_available = orig_is_available

            print("[AudioEnhancer] ✅ DeepFilterNet listo (CPU).")
        return self._df_model, self._df_state

    # ── Normalización ─────────────────────────────────────────────────────────

    def _normalize_rms(self, audio: np.ndarray, target_db: float = -20.0) -> np.ndarray:
        """Normaliza a un nivel RMS objetivo en dBFS."""
        rms = _rms(audio)
        if rms < 1e-9:
            return audio
        target_rms = 10 ** (target_db / 20.0)
        gain = np.float32(np.clip(target_rms / rms, 0.0, 15.0))
        salida = audio * gain  # una sola copia del audio, no tres
        np.clip(salida, -1.0, 1.0, out=salida)
        return salida

    def _normalize_peak(self, audio: np.ndarray, peak: float = 0.95) -> np.ndarray:
        """Normalización final por pico para evitar clipping."""
        max_val = np.max(np.abs(audio))
        if max_val < 1e-9:
            return audio
        return audio * np.float32(peak / max_val)  # una sola copia del audio

    # ── Filtros de frecuencia ─────────────────────────────────────────────────

    def _highpass_filter(self, audio: np.ndarray, sr: int, cutoff_hz: int) -> np.ndarray:
        """Filtro pasa-altos para eliminar rumble de baja frecuencia."""
        if not HAS_SCIPY or cutoff_hz <= 0:
            return audio
        nyq = sr / 2
        normal_cutoff = max(min(cutoff_hz / nyq, 0.999), 0.001)
        sos = butter(4, normal_cutoff, btype='high', output='sos')
        return por_tramos(lambda x: sosfiltfilt(sos, x).astype(np.float32), audio, sr)

    def _lowpass_filter(self, audio: np.ndarray, sr: int, cutoff_hz: int) -> np.ndarray:
        """Filtro pasa-bajos para recortar sibilancias y ruido de alta frecuencia."""
        if not HAS_SCIPY or cutoff_hz <= 0:
            return audio
        nyq = sr / 2
        normal_cutoff = max(min(cutoff_hz / nyq, 0.999), 0.001)
        sos = butter(4, normal_cutoff, btype='low', output='sos')
        return por_tramos(lambda x: sosfiltfilt(sos, x).astype(np.float32), audio, sr)

    def _bandpass_boost(self, audio: np.ndarray, sr: int,
                        low_hz: int = 800, high_hz: int = 4000,
                        gain_db: float = 3.0) -> np.ndarray:
        """
        Realce de intelligibilidad vocal: boost en la banda de presencia
        (aprox 800Hz-4kHz donde la voz humana tiene máxima energía fonética).
        gain_db: ganancia en dB (1-6 dB recomendado, máximo 12 dB).
        """
        if not HAS_SCIPY or gain_db <= 0:
            return audio
        nyq = sr / 2
        low = max(min(low_hz / nyq, 0.999), 0.001)
        high = max(min(high_hz / nyq, 0.999), 0.001)
        if low >= high:
            return audio
        sos = butter(2, [low, high], btype='band', output='sos')
        boosted = sosfiltfilt(sos, audio)
        gain_linear = 10 ** (gain_db / 20.0)
        # Mezcla: original + boost de banda
        return np.clip(audio + boosted * (gain_linear - 1.0), -1.0, 1.0).astype(np.float32)

    # ── Compresión dinámica ───────────────────────────────────────────────────

    def _dynamic_compression(self, audio: np.ndarray,
                              threshold_db: float = -20.0,
                              ratio: float = 3.0,
                              attack_ms: float = 5.0,
                              release_ms: float = 50.0,
                              sr: int = 16000) -> np.ndarray:
        """
        Compresor de dinámica simple que:
        - Reduce señales por encima del threshold (ratio:1)
        - Amplifica secciones silenciosas (make-up gain automático)
        Muy útil para audios escolares donde el profesor varía el volumen.
        """
        threshold_linear = 10 ** (threshold_db / 20.0)
        attack_coef = np.exp(-1.0 / (sr * attack_ms / 1000.0))
        release_coef = np.exp(-1.0 / (sr * release_ms / 1000.0))

        envelope = np.zeros_like(audio)
        gain_arr = np.ones_like(audio)
        env = 0.0

        for i in range(len(audio)):
            level = abs(audio[i])
            if level > env:
                env = attack_coef * env + (1 - attack_coef) * level
            else:
                env = release_coef * env + (1 - release_coef) * level
            envelope[i] = env

        # Calcular ganancia de compresión
        for i in range(len(audio)):
            env_i = envelope[i]
            if env_i > threshold_linear:
                gain_arr[i] = threshold_linear * (env_i / threshold_linear) ** (1.0 / ratio) / env_i
            # else: gain = 1.0 (sin compresión debajo del threshold)

        compressed = audio * gain_arr

        # Make-up gain automático: normaliza el RMS al nivel original
        orig_rms = np.sqrt(np.mean(audio ** 2))
        comp_rms = np.sqrt(np.mean(compressed ** 2))
        if comp_rms > 1e-9:
            makeup = min(orig_rms / comp_rms, 3.0)  # máximo 3x
            compressed = np.clip(compressed * makeup, -1.0, 1.0)

        return compressed.astype(np.float32)

    # ── Reducción de ruido ────────────────────────────────────────────────────

    def _denoise_light_dsp(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """DSP ligero: sustracción espectral suave (prop_decrease=0.3)."""
        if not HAS_NOISEREDUCE:
            return audio
        noise_clip = perfil_de_ruido(audio, sr, 0.5)
        return nr.reduce_noise(y=audio, y_noise=noise_clip, sr=sr,
                               prop_decrease=0.3, stationary=True, n_jobs=1).astype(np.float32)

    def _denoise_dsp(self, audio: np.ndarray, sr: int, strength: float = 1.5) -> np.ndarray:
        """Wiener filter estándar, balanceado ruido/calidad."""
        if not HAS_NOISEREDUCE:
            return audio
        noise_clip = perfil_de_ruido(audio, sr, 0.5)
        prop = np.clip(strength / 3.0, 0.1, 1.0)
        return nr.reduce_noise(y=audio, y_noise=noise_clip, sr=sr,
                               prop_decrease=prop, stationary=False, n_jobs=1).astype(np.float32)

    def _denoise_heavy_dsp(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Wiener filter agresivo: doble pasada con prop_decrease alto."""
        if not HAS_NOISEREDUCE:
            return audio
        noise_clip = perfil_de_ruido(audio, sr, 1.0)
        # Primera pasada: reducción fuerte
        pass1 = nr.reduce_noise(y=audio, y_noise=noise_clip, sr=sr,
                                prop_decrease=0.9, stationary=False, n_jobs=1)
        # Segunda pasada: limpieza residual
        pass2 = nr.reduce_noise(y=pass1, sr=sr,
                                prop_decrease=0.5, stationary=True, n_jobs=1)
        return pass2.astype(np.float32)

    def _denoise_mmse(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """
        MMSE-LSA espectral en PyTorch.
        Estimación de ruido adaptativa + curva de ganancia MMSE + suavizado temporal.
        No requiere modelos ni dependencias extra.
        """
        import torch

        audio_tensor = torch.from_numpy(audio).float()
        n_fft, hop_length, win_length = 512, 128, 512
        window = torch.hann_window(win_length)

        stft = torch.stft(audio_tensor, n_fft=n_fft, hop_length=hop_length,
                          win_length=win_length, window=window, return_complex=True)
        magnitude = stft.abs()
        phase = stft.angle()

        # Piso de ruido: percentil 15 sobre el tiempo
        noise_floor = torch.quantile(magnitude, 0.15, dim=1, keepdim=True).clamp(min=1e-10)
        noise_floor = noise_floor.expand_as(magnitude)

        snr = (magnitude / noise_floor).clamp(min=0.0)
        gain = (1.0 - 1.0 / (snr + 1.0) ** 2).clamp(min=0.01, max=1.0)

        # Suavizado temporal para evitar artefactos
        gain_smoothed = torch.nn.functional.avg_pool1d(
            gain.unsqueeze(0), kernel_size=7, stride=1, padding=3
        ).squeeze(0)

        stft_clean = torch.polar(magnitude * gain_smoothed, phase)
        audio_clean = torch.istft(stft_clean, n_fft=n_fft, hop_length=hop_length,
                                  win_length=win_length, window=window, length=len(audio_tensor))
        return audio_clean.numpy().astype(np.float32)

    def _denoise_deepfilter(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """DeepFilterNet: red neuronal entrenada para speech enhancement. Corre en CPU."""
        import torch
        import torchaudio
        from df.enhance import enhance

        model, _ = self._load_df_model()
        
        # DeepFilterNet trabaja a 48kHz
        # Asegurar CPU para no competir con el modelo ASR en GPU
        audio_tensor = torch.from_numpy(audio).unsqueeze(0).cpu()  # (1, T)

        # Resamplear si es necesario (el modelo espera 48kHz)
        target_sr = self._df_state.sr() if self._df_state else 48000
        if sr != target_sr:
            resampler = torchaudio.transforms.Resample(sr, target_sr).cpu()
            audio_tensor = resampler(audio_tensor)

        # Mejorar - PARCHE DE TIEMPO DE EJECUCIÓN
        # df.enhance.enhance() llama a get_device() internamente.
        # Volvemos a engañar a torch para que crea que no hay CUDA durante esta llamada.
        orig_is_available = torch.cuda.is_available
        torch.cuda.is_available = lambda: False
        try:
            if self._df_state is None:
                raise RuntimeError("DeepFilterNet no se inicializó correctamente.")
            enhanced = enhance(model, self._df_state, audio_tensor)
        finally:
            torch.cuda.is_available = orig_is_available

        # Resamplear de vuelta al original
        if sr != target_sr:
            resampler_back = torchaudio.transforms.Resample(target_sr, sr).cpu()
            enhanced = resampler_back(enhanced)

        return enhanced.squeeze(0).detach().cpu().numpy().astype(np.float32)

    # ── Pipeline principal ────────────────────────────────────────────────────

    def enhance(
        self,
        input_path: str,
        output_path: str = None,
        # Reducción de ruido
        denoise_mode: str = 'dsp',
        denoise_strength: float = 1.5,
        # Filtros de frecuencia
        highpass_hz: int = 80,
        lowpass_hz: int = 0,
        # Normalización
        normalize_input: bool = True,
        normalize_output: bool = True,
        # Realce de intelligibilidad
        voice_boost_db: float = 0.0,
        voice_boost_low_hz: int = 800,
        voice_boost_high_hz: int = 4000,
        # Compresión dinámica
        use_compressor: bool = False,
        compressor_threshold_db: float = -20.0,
        compressor_ratio: float = 3.0,
    ) -> str:
        """
        Pipeline principal de mejora de audio.
        Devuelve la ruta al archivo procesado.
        """
        if denoise_mode == 'none' and not normalize_input and not normalize_output \
                and highpass_hz <= 0 and lowpass_hz <= 0 and voice_boost_db <= 0 \
                and not use_compressor:
            return input_path  # Nada que hacer

        print(f"[AudioEnhancer] Procesando audio (modo: {denoise_mode.upper()})...")

        # ── Leer audio ────────────────────────────────────────────────────────
        audio, sr = sf.read(input_path, dtype='float32', always_2d=False)
        if audio.ndim == 2:
            audio = np.mean(audio, axis=1)
        original_sr = sr

        # ── Capa 1: Normalización de entrada ─────────────────────────────────
        if normalize_input:
            audio = self._normalize_rms(audio, target_db=-20.0)
            print("[AudioEnhancer] ✓ Normalización RMS")

        # ── Capa 2: Filtro pasa-altos ─────────────────────────────────────────
        if highpass_hz > 0:
            audio = self._highpass_filter(audio, sr, highpass_hz)
            print(f"[AudioEnhancer] ✓ Highpass {highpass_hz}Hz")

        # ── Capa 3: Filtro pasa-bajos ─────────────────────────────────────────
        if lowpass_hz > 0:
            audio = self._lowpass_filter(audio, sr, lowpass_hz)
            print(f"[AudioEnhancer] ✓ Lowpass {lowpass_hz}Hz")

        # ── Capa 4: Reducción de ruido ─────────────────────────────────────────
        try:
            # Por tramos: el consumo de memoria no debe crecer con el largo de la clase (medido sobre 92 min:
            # 2,7 GB con los modos DSP y 11,6 GB con mmse, que no caben en un equipo modesto).
            quitar_ruido = {
                'light_dsp': lambda x: self._denoise_light_dsp(x, sr),
                'dsp': lambda x: self._denoise_dsp(x, sr, strength=denoise_strength),
                'heavy_dsp': lambda x: self._denoise_heavy_dsp(x, sr),
                'mmse': lambda x: self._denoise_mmse(x, sr),
            }.get(denoise_mode)
            if quitar_ruido:
                audio = por_tramos(quitar_ruido, audio, sr)
            elif denoise_mode == 'deepfilter':
                audio = self._denoise_deepfilter(audio, sr)
            if denoise_mode != 'none':
                print(f"[AudioEnhancer] ✓ Reducción de ruido ({denoise_mode})")
        except Exception as e:
            print(f"[AudioEnhancer] ⚠️ {denoise_mode} falló: {e} — continuando sin esta capa.")

        # ── Capa 5: Realce de intelligibilidad vocal ───────────────────────────
        if voice_boost_db > 0:
            audio = self._bandpass_boost(audio, sr,
                                         low_hz=voice_boost_low_hz,
                                         high_hz=voice_boost_high_hz,
                                         gain_db=voice_boost_db)
            print(f"[AudioEnhancer] ✓ Realce vocal +{voice_boost_db:.1f}dB ({voice_boost_low_hz}-{voice_boost_high_hz}Hz)")

        # ── Capa 6: Compresión dinámica ────────────────────────────────────────
        if use_compressor:
            audio = self._dynamic_compression(audio,
                                               threshold_db=compressor_threshold_db,
                                               ratio=compressor_ratio,
                                               sr=sr)
            print(f"[AudioEnhancer] ✓ Compresor ({compressor_threshold_db}dB, {compressor_ratio}:1)")

        # ── Capa 7: Normalización final ────────────────────────────────────────
        if normalize_output:
            audio = self._normalize_peak(audio, peak=0.95)
            print("[AudioEnhancer] ✓ Normalización de pico final")

        # ── Limpieza explícita de Memoria RAM (OOM Guard) ─────────────────────
        import gc
        gc.collect()

        # ── Guardar ────────────────────────────────────────────────────────────
        if output_path is None:
            # Forzamos .wav para evitar problemas con formatos que soundfile no escribe bien (como .mp3)
            # NeMo y Whisper leen WAV sin problemas.
            tmp = tempfile.NamedTemporaryFile(
                delete=False, suffix='_enhanced.wav',
                dir=os.path.dirname(input_path) or '.'
            )
            output_path = tmp.name
            tmp.close()

        # Debug diagnostics
        print(f"[AudioEnhancer] Guardando: {output_path} (SR: {sr}, Shape: {audio.shape}, Type: {audio.dtype})")
        # No usamos subtype='PCM_16' explicitamente para que sf lo auto-detecte según la extensión
        sf.write(output_path, audio, sr)
        
        print(f"[AudioEnhancer] ✓ Guardado: {os.path.basename(output_path)}")
        return output_path

    def is_available(self, mode: str) -> tuple[bool, str]:
        if mode == 'none':
            return True, "Sin procesamiento"
        elif mode in ('light_dsp', 'dsp', 'heavy_dsp'):
            if HAS_NOISEREDUCE:
                return True, "noisereduce disponible"
            return False, "pip install noisereduce"
        elif mode == 'mmse':
            return True, "PyTorch MMSE (siempre disponible)"
        elif mode == 'deepfilter':
            if HAS_DEEPFILTER:
                return True, "DeepFilterNet disponible"
            return False, "pip install deepfilternet (requiere Rust)"
        return False, f"Modo desconocido: {mode}"
