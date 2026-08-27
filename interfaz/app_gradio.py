import os

import gradio as gr

from nucleo import configuracion as app_config
from infraestructura import youtube
from servicios.servicio_transcripcion import TranscriptionService
from servicios.servicio_material_estudio import generate_study_material
from servicios import servicio_historial as history_service


def create_ui():
    transcription_service = TranscriptionService()

    def on_load_cloud(model_choice):
        if not model_choice: return "Ningún modelo seleccionado."
        # Limpiar el nombre visual (" ➔ [...]") para obtener el identificador del modelo
        model_id = model_choice.split(" ➔ ")[0].strip()
        return transcription_service.load_model(model_id)

    def on_load_local(local_path):
        if not local_path: return "La ruta provista es nula."
        return transcription_service.load_model(local_path.strip())

    def process_url(url, language):
        if not url:
            yield "No se ha ingresado una URL válida.", None, None, ""
            return
        path = youtube.download_audio_from_url(url)
        if not path:
            yield "❌ Error descargando la URL enviada.", None, None, ""
            return
        for update in process_audio([path], language):
            yield update

    def process_mic(audio_filepath, language):
        if not audio_filepath:
            yield "No se detectó grabación del micrófono.", None, None, ""
            return
        for update in process_audio([audio_filepath], language):
            yield update

    def process_audio(audio_paths, language):
        if not audio_paths:
            yield "No se ha subido ninguna pista de audio.", None, None, ""
            return
        if not isinstance(audio_paths, list):
            audio_paths = [audio_paths]

        cumulative_text = ""
        last_metrics = ""
        all_txt_files = []
        all_srt_files = []

        for i, audio_path in enumerate(audio_paths):
            current_full_path = audio_path.name if hasattr(audio_path, 'name') else str(audio_path)
            fname = os.path.basename(current_full_path)

            # Encabezados para diferenciar archivos en el preview acumulado
            file_header = f"\n--- ARCHIVO {i+1}: {fname} ---\n"

            generator = transcription_service.transcribe_file(current_full_path, language=language)
            current_file_text = ""
            current_file_srt = ""

            for update in generator:
                current_file_text = update.get("text", "")
                current_file_srt = update.get("srt", "")
                last_metrics = update.get("metrics_html", "")
                status_str = update.get("status", "")
                yield f"⏳ {status_str}\n\n{cumulative_text + file_header + current_file_text}", None, None, last_metrics

            history_service.save(fname, transcription_service.current_backend, current_file_text, current_file_srt)
            os.makedirs("outputs", exist_ok=True)
            p_txt = os.path.join("outputs", f"transcripcion_{i+1}_{fname}.txt")
            p_srt = os.path.join("outputs", f"transcripcion_{i+1}_{fname}.srt")
            with open(p_txt, "w", encoding="utf-8") as f: f.write(current_file_text)
            with open(p_srt, "w", encoding="utf-8") as f: f.write(current_file_srt)

            all_txt_files.append(p_txt)
            all_srt_files.append(p_srt)

            # El audio nunca se guarda: se borra apenas termina de procesarse.
            if os.path.exists(current_full_path):
                try:
                    os.remove(current_full_path)
                except Exception:
                    pass

            cumulative_text += file_header + current_file_text + "\n"

        yield cumulative_text, all_txt_files, all_srt_files, last_metrics

    def save_settings(beam_size, vad_filter, compute_type, language, ollama_model, ollama_max_tokens, ollama_chunk_chars):
        app_config.set_param("beam_size", beam_size)
        app_config.set_param("vad_filter", vad_filter)
        app_config.set_param("compute_type", compute_type)
        app_config.set_param("language", str(language).strip() if language else "auto")
        app_config.set_param("ollama_model", str(ollama_model).strip())
        app_config.set_param("ollama_max_tokens", int(ollama_max_tokens))
        app_config.set_param("ollama_chunk_chars", int(ollama_chunk_chars))
        return "✅ Ajustes guardados exitosamente. Tendrán efecto al reiniciar o cargar nuevo modelo."

    def on_generate_study_material(text):
        if not text:
            empty = "_Genera primero una transcripción._"
            return "No hay transcripción todavía.", "", "", empty
        summary, key_points, review_sheet, flashcards = generate_study_material(text)
        if not key_points:
            key_points = "_No se pudieron separar puntos clave — revisa el resumen completo arriba._"
        if not review_sheet:
            review_sheet = "_No se pudo generar la hoja de repaso._"
        if flashcards:
            flashcards_md = "\n\n".join(
                f"**{i}. P:** {c['pregunta']}\n**R:** {c['respuesta']}"
                for i, c in enumerate(flashcards, start=1)
            )
        else:
            flashcards_md = "_No se pudieron generar tarjetas de estudio._"
        return summary, key_points, review_sheet, flashcards_md


    # ──────────────────────────────────────────────────────────────────
    # CSS PREMIUM — Dark Glass Theme
    # ──────────────────────────────────────────────────────────────────
    PREMIUM_CSS = """
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

    /* ── Variables ──
       One accent color, used sparingly (primary buttons, active tab, focus
       rings) — not painted across every border and label. Surfaces are
       neutral slate, not tinted violet, so panels don't compound into a
       wall of purple boxes. */
    :root {
        --accent:       #7c3aed;
        --accent-text:  #b4a4f5;
        --bg-base:      #0b0d12;
        --bg-panel:     rgba(22, 25, 32, 0.55);
        --border:       rgba(148, 163, 184, 0.14);
        --border-soft:  rgba(148, 163, 184, 0.09);
        --text-primary: #e5e7eb;
        --text-muted:   #8992a3;
        --radius:       10px;
        --radius-sm:    6px;
        --shadow-sm:    0 2px 10px rgba(0,0,0,0.25);
    }

    /* ── Root & Body ── */
    html, body, .gradio-container {
        font-family: 'Inter', system-ui, -apple-system, sans-serif !important;
        background: var(--bg-base) !important;
        color: var(--text-primary) !important;
        min-height: 100vh;
    }

    /* ── Header ── */
    #main-header {
        text-align: center;
        padding: 2rem 1rem 1.25rem;
    }
    #main-header h1 {
        color: var(--text-primary) !important;
        font-size: 1.9rem !important;
        font-weight: 700 !important;
        letter-spacing: -0.02em;
        margin-bottom: 0.4rem;
    }
    #main-header p {
        color: var(--text-muted) !important;
        font-size: 0.95rem !important;
        font-weight: 400;
    }

    /* ── Main wrapper ── */
    .main {
        max-width: 1400px;
        margin: 0 auto;
        padding: 0 1.5rem 3rem;
    }

    /* ── Panels / Columns ── */
    .panel, [data-testid="column"] > .wrap {
        background: var(--bg-panel) !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--radius) !important;
        box-shadow: var(--shadow-sm) !important;
    }

    /* Some non-interactive output blocks (notably the Audio player) render
       with a literal body-text-color border instead of the themed
       --block-border-color, which reads as a stark white ring against a
       dark theme — force every block border back to our neutral palette. */
    .border_contrast, .block {
        border-color: var(--border) !important;
        box-shadow: none !important;
    }

    /* ── Tabs ── */
    .tabs > .tab-wrapper {
        border-bottom: 1px solid var(--border-soft) !important;
        padding: 0 0.25rem !important;
        gap: 1.25rem !important;
    }
    .tabs > .tab-wrapper .tab-container[role="tablist"] > button {
        background: transparent !important;
        color: var(--text-muted) !important;
        border: none !important;
        border-radius: 0 !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 500 !important;
        font-size: 0.86rem !important;
        padding: 0.65rem 0.1rem !important;
        transition: color 0.15s !important;
        position: relative;
    }
    .tabs > .tab-wrapper .tab-container[role="tablist"] > button:hover {
        color: var(--text-primary) !important;
    }
    .tabs > .tab-wrapper .tab-container[role="tablist"] > button.selected {
        color: var(--text-primary) !important;
    }
    .tabs > .tab-wrapper .tab-container[role="tablist"] > button.selected::after {
        content: '';
        position: absolute;
        bottom: -1px;
        left: 0;
        width: 100%;
        height: 2px;
        background: var(--accent);
    }

    /* ── Inputs / Textareas / Selects ──
       Excludes checkbox/radio/range: those are small native toggle controls
       with their own Gradio-defined size (1rem, fully-rounded) — painting
       them with text-input padding/border-radius turns them into oversized
       rounded rectangles instead of a checkbox/radio dot. */
    input:not([type=checkbox]):not([type=radio]):not([type=range]), textarea, select {
        background: rgba(0, 0, 0, 0.18) !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--radius-sm) !important;
        color: var(--text-primary) !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 0.9rem !important;
        transition: border-color 0.2s !important;
        padding: 0.6rem 0.85rem !important;
        text-overflow: ellipsis;
    }
    input:not([type=checkbox]):not([type=radio]):not([type=range]):focus, textarea:focus, select:focus {
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 3px rgba(124, 58, 237, 0.15) !important;
        outline: none !important;
    }

    /* ── Checkboxes & Radio ── small native-sized toggles, not text inputs.
       Gradio sets appearance:none globally on these, which also strips the
       native checked mark that accent-color relies on to render — restore
       native appearance so the check/dot is actually visible. */
    input[type=checkbox], input[type=radio] {
        appearance: auto !important;
        width: 1.05rem !important;
        height: 1.05rem !important;
        min-width: 1.05rem !important;
        accent-color: var(--accent) !important;
        cursor: pointer;
    }
    input[type=checkbox]:focus-visible, input[type=radio]:focus-visible {
        outline: 2px solid var(--accent) !important;
        outline-offset: 1px;
    }

    /* ── Dropdowns ── */
    .dropdown-arrow { color: var(--text-muted) !important; }
    ul.options {
        background: #14161e !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--radius-sm) !important;
        box-shadow: var(--shadow-sm) !important;
    }
    ul.options li:hover {
        background: rgba(124, 58, 237, 0.14) !important;
        color: var(--accent-text) !important;
    }

    /* ── Buttons ── */
    button.primary {
        background: var(--accent) !important;
        border: none !important;
        color: #fff !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 600 !important;
        border-radius: var(--radius-sm) !important;
        transition: filter 0.15s ease !important;
    }
    button.primary:hover {
        filter: brightness(1.12) !important;
    }

    button.secondary {
        background: rgba(148, 163, 184, 0.08) !important;
        border: 1px solid var(--border) !important;
        color: var(--text-primary) !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 500 !important;
        border-radius: var(--radius-sm) !important;
        transition: background 0.15s !important;
    }
    button.secondary:hover {
        background: rgba(148, 163, 184, 0.14) !important;
    }

    /* Small buttons (post-processing) */
    button.sm {
        background: transparent !important;
        border: 1px solid var(--border) !important;
        color: var(--text-muted) !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 500 !important;
        border-radius: var(--radius-sm) !important;
        font-size: 0.82rem !important;
        transition: color 0.15s, border-color 0.15s !important;
    }
    button.sm:hover {
        color: var(--text-primary) !important;
        border-color: rgba(148, 163, 184, 0.3) !important;
    }

    /* ── Labels ── plain small-caps text, no pill background */
    label, .label-wrap span, .form > label > span {
        color: var(--text-muted) !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 0.76rem !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    /* ── Markdown headings ── */
    .prose h3, .prose h4 {
        color: var(--text-primary) !important;
        font-weight: 600 !important;
        letter-spacing: -0.01em;
        margin-top: 1.2rem !important;
    }
    .prose p, .prose li {
        color: var(--text-muted) !important;
        font-size: 0.9rem !important;
        line-height: 1.7 !important;
    }
    .prose strong { color: #e2e8f0 !important; }
    .prose em { color: var(--accent-text) !important; font-style: italic; }
    .prose code {
        background: rgba(148, 163, 184, 0.12) !important;
        color: var(--accent-text) !important;
        border-radius: 4px;
        padding: 0.1em 0.4em;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.85em;
    }
    hr { border-color: var(--border-soft) !important; margin: 1rem 0 !important; }

    /* ── Sliders ── */
    input[type=range] {
        accent-color: var(--accent) !important;
    }
    .gradio-slider .wrap {
        background: transparent !important;
    }

    /* ── Checkboxes & Radio ── */
    input[type=checkbox], input[type=radio] {
        accent-color: var(--accent) !important;
    }

    /* ── Accordion ── plain disclosure row, no filled pill */
    .gr-accordion > .label-wrap {
        background: transparent !important;
        border-radius: var(--radius-sm) !important;
        border: 1px solid var(--border) !important;
        padding: 0.5rem 0.75rem !important;
        transition: border-color 0.15s !important;
    }
    .gr-accordion > .label-wrap:hover {
        border-color: rgba(148, 163, 184, 0.3) !important;
    }

    /* ── DataFrames / Tables ── */
    table {
        border-radius: var(--radius-sm) !important;
        overflow: hidden;
    }
    thead tr th {
        background: rgba(148, 163, 184, 0.08) !important;
        color: var(--text-primary) !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 0.78rem !important;
        font-weight: 700 !important;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        border-bottom: 1px solid var(--border) !important;
    }
    tbody tr td {
        background: transparent !important;
        color: var(--text-primary) !important;
        border-bottom: 1px solid var(--border-soft) !important;
        font-size: 0.88rem !important;
    }
    tbody tr:hover td {
        background: rgba(148, 163, 184, 0.05) !important;
    }

    /* ── Audio player ── */
    audio {
        border-radius: var(--radius-sm) !important;
        width: 100%;
    }

    /* ── Scrollbars ── */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb {
        background: rgba(148, 163, 184, 0.25);
        border-radius: 10px;
    }
    ::-webkit-scrollbar-thumb:hover { background: rgba(148, 163, 184, 0.4); }

    /* ── File upload zone ── */
    .file-preview-holder, .upload-container {
        background: transparent !important;
        border: 1.5px dashed var(--border) !important;
        border-radius: var(--radius) !important;
        transition: border-color 0.2s !important;
    }
    .file-preview-holder:hover, .upload-container:hover {
        border-color: rgba(148, 163, 184, 0.35) !important;
    }

    /* ── Status box special style ── */
    #status-box textarea {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.82rem !important;
        color: #a3adc2 !important;
        line-height: 1.6 !important;
    }

    /* ── Transcript output special style ── */
    #transcript-output textarea {
        font-family: 'Inter', sans-serif !important;
        font-size: 0.92rem !important;
        line-height: 1.75 !important;
        color: #e2e8f0 !important;
    }

    /* ── Section dividers in markdown ── */
    .prose blockquote {
        border-left: 3px solid var(--border) !important;
        background: transparent !important;
        padding: 0.5rem 1rem !important;
        color: var(--text-muted) !important;
        font-style: normal !important;
    }
    """

    # ──────────────────────────────────────────────────────────────────
    # TEMA GRADIO
    # ──────────────────────────────────────────────────────────────────
    premium_theme = gr.themes.Soft(
        primary_hue=gr.themes.colors.violet,
        secondary_hue=gr.themes.colors.cyan,
        neutral_hue=gr.themes.colors.slate,
        font=[gr.themes.GoogleFont("Inter"), "system-ui", "sans-serif"],
        font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "monospace"],
    ).set(
        # Neutral slate surfaces; violet is reserved for primary actions and
        # focus states so panels don't compound into a wall of purple boxes.
        body_background_fill="#0b0d12",
        body_background_fill_dark="#0b0d12",
        body_text_color="#e5e7eb",
        body_text_color_dark="#e5e7eb",
        body_text_color_subdued="#8992a3",
        color_accent_soft="rgba(124,58,237,0.12)",
        background_fill_primary="rgba(22, 25, 32, 0.55)",
        background_fill_primary_dark="rgba(22, 25, 32, 0.55)",
        background_fill_secondary="rgba(0, 0, 0, 0.18)",
        background_fill_secondary_dark="rgba(0, 0, 0, 0.18)",
        border_color_primary="rgba(148, 163, 184, 0.14)",
        border_color_primary_dark="rgba(148, 163, 184, 0.14)",
        shadow_drop="0 2px 10px rgba(0,0,0,0.25)",
        shadow_drop_lg="0 4px 16px rgba(0,0,0,0.3)",
        block_background_fill="rgba(22, 25, 32, 0.5)",
        block_background_fill_dark="rgba(22, 25, 32, 0.5)",
        block_border_color="rgba(148, 163, 184, 0.14)",
        block_border_color_dark="rgba(148, 163, 184, 0.14)",
        block_label_background_fill="transparent",
        block_label_background_fill_dark="transparent",
        block_label_text_color="#8992a3",
        block_title_text_color="#e5e7eb",
        panel_background_fill="rgba(16, 18, 24, 0.6)",
        panel_border_color="rgba(148, 163, 184, 0.14)",
        button_primary_background_fill="#7c3aed",
        button_primary_background_fill_hover="#8b5cf6",
        button_primary_text_color="#ffffff",
        button_primary_border_color="transparent",
        button_secondary_background_fill="rgba(148, 163, 184, 0.08)",
        button_secondary_background_fill_hover="rgba(148, 163, 184, 0.14)",
        button_secondary_text_color="#e5e7eb",
        button_secondary_border_color="rgba(148, 163, 184, 0.14)",
        input_background_fill="rgba(0, 0, 0, 0.18)",
        input_background_fill_dark="rgba(0, 0, 0, 0.18)",
        input_border_color="rgba(148, 163, 184, 0.14)",
        input_border_color_focus="#7c3aed",
        input_shadow_focus="0 0 0 3px rgba(124, 58, 237, 0.15)",
        input_placeholder_color="#475569",
        checkbox_background_color="rgba(0, 0, 0, 0.18)",
        checkbox_background_color_selected="#7c3aed",
        slider_color="#7c3aed",
        table_odd_background_fill="transparent",
        table_even_background_fill="rgba(148, 163, 184, 0.04)",
        table_border_color="rgba(148, 163, 184, 0.12)",
    )

    with gr.Blocks(
        title="Universal Local Transcriber — Premium",
        theme=premium_theme,
        css=PREMIUM_CSS
    ) as app:

        # ── Header enriquecido ──────────────────────────────────────────
        with gr.Column(elem_id="main-header"):
            gr.HTML("""
            <div style="text-align: center; padding: 1.75rem 1rem 0.75rem; font-family: 'Inter', sans-serif;">
                <h1 style="font-size: 1.6rem; font-weight: 700; letter-spacing: -0.01em; color: #e5e7eb; margin: 0 0 0.4rem;">
                    Universal Local Transcriber
                </h1>
                <p style="font-size: 0.9rem; color: #8992a3; max-width: 620px; margin: 0 auto; line-height: 1.6;">
                    Transcripción local con faster-whisper — corre en CPU, sin enviar audio a la nube.
                </p>
            </div>
            """)

        with gr.Tabs():
            with gr.TabItem("📝 Transcripción y Análisis"):
                with gr.Row(equal_height=True):
                    # Panel izquierdo (Configuración)
                    with gr.Column(scale=1, variant="panel"):
                        gr.Markdown("### ⚙️ 1. Seleccionar Modelo de IA")

                        with gr.Tabs():
                            with gr.TabItem("☁️ Catálogo"):
                                cloud_dropdown = gr.Dropdown(
                                    choices=transcription_service.available_models,
                                    label=f"Modelo Whisper ({transcription_service.engine_name}):"
                                )
                                btn_load_cloud = gr.Button("Cargar Modelo", variant="primary")

                            with gr.TabItem("📁 Personalizado"):
                                gr.Markdown("*Soporta modelos faster-whisper (CTranslate2) locales — descargados manualmente o convertidos con `ct2-transformers-converter`. Selecciona la **carpeta** que contiene `model.bin`.*")

                                file_explorer = gr.FileExplorer(
                                    root_dir="/",
                                    file_count="single",
                                    label="Navegador Rápido de Sistema de Archivos"
                                )

                                local_path_input = gr.Textbox(
                                    label="Ruta (Directorio o archivo de modelo)",
                                    placeholder="/home/usuario/modelos/mi-whisper-local",
                                    interactive=True
                                )

                                btn_load_local = gr.Button("Analizar Ruta y Cargar", variant="primary")

                                def sync_path(x):
                                    if not x: return ""
                                    rel_path = str(x[0]) if isinstance(x, list) else str(x)
                                    # Evitar dobles barras si root ya es /
                                    return os.path.join("/", rel_path.lstrip("/"))

                                file_explorer.change(fn=sync_path, inputs=file_explorer, outputs=local_path_input)

                        gr.Markdown("---")
                        status_box = gr.Textbox(
                            label="Monitor de Estado del Sistema",
                            interactive=False,
                            value=f"✦ Sistema listo. Esperando instrucciones...\n⚡ Hardware de inferencia: {transcription_service.device.upper()}\n🧩 Motor: {transcription_service.engine_name}",
                            lines=4,
                            elem_id="status-box"
                        )

                        gr.Markdown("---")
                        gr.Markdown("### 🧙 Limpieza de Audio Pre-Transcripción")
                        with gr.Accordion("🔊 Opciones de Limpieza de Audio", open=False):
                            enhance_enabled = gr.Checkbox(
                                label="Activar limpieza de audio",
                                value=False,
                                info="Aplica filtros antes de transcribir. Ideal para aulas, reuniones, campo."
                            )

                            with gr.Group(visible=False) as enhance_controls_group:
                                gr.Markdown("#### 🎚️ Reducción de Ruido")
                                enhance_mode = gr.Radio(
                                    choices=[
                                        ("💨 Ninguna (solo filtros)", "none"),
                                        ("🔹 Ligera DSP (ruido leve)", "light_dsp"),
                                        ("🔶 Estándar DSP — Wiener (equilibrado)", "dsp"),
                                        ("🔴 Agresiva DSP (ruido intenso)", "heavy_dsp"),
                                        ("🧠 MMSE Espectral PyTorch (alta calidad)", "mmse"),
                                        ("⭐ DeepFilterNet IA (máxima calidad)", "deepfilter"),
                                    ],
                                    value="dsp",
                                    label="Modo de reducción de ruido",
                                )
                                enhance_strength = gr.Slider(
                                    minimum=0.5, maximum=3.0, step=0.5, value=1.5,
                                    label="Intensidad DSP (solo modos DSP estándar)",
                                    info="0.5 = muy suave · 1.5 = estándar · 3.0 = máximo"
                                )

                                gr.Markdown("#### 🎛️ Filtros de Frecuencia")
                                with gr.Row():
                                    enhance_highpass = gr.Slider(
                                        minimum=0, maximum=400, step=10, value=80,
                                        label="Pasa-altos (Hz)",
                                        info="Elimina rumble: AC, ventiladores, micrófonos de mesa. 0 = off"
                                    )
                                    enhance_lowpass = gr.Slider(
                                        minimum=0, maximum=16000, step=500, value=0,
                                        label="Pasa-bajos (Hz)",
                                        info="Recorta sibilancias y ruido agudo extremo. 0 = off"
                                    )

                                gr.Markdown("#### 🗣️ Realce de Inteligibilidad Vocal")
                                with gr.Row():
                                    voice_boost_db = gr.Slider(
                                        minimum=0, maximum=12, step=1, value=0,
                                        label="Boost vocal (dB)",
                                        info="Enfatiza la zona de presencia de la voz. 0 = off"
                                    )
                                    voice_boost_low = gr.Slider(
                                        minimum=200, maximum=2000, step=100, value=800,
                                        label="Frecuencia baja del boost (Hz)"
                                    )
                                    voice_boost_high = gr.Slider(
                                        minimum=2000, maximum=12000, step=500, value=4000,
                                        label="Frecuencia alta del boost (Hz)"
                                    )

                                gr.Markdown("#### 📊 Compresión Dinámica")
                                use_compressor = gr.Checkbox(
                                    label="Activar compresor dinámico",
                                    value=False,
                                    info="Iguala volúmenes: acerca las partes muy bajas a las muy altas. Ideal si el locutor varía mucho el volumen."
                                )
                                with gr.Row():
                                    comp_threshold = gr.Slider(
                                        minimum=-40, maximum=-6, step=2, value=-20,
                                        label="Umbral de compresión (dBFS)"
                                    )
                                    comp_ratio = gr.Slider(
                                        minimum=1.5, maximum=8.0, step=0.5, value=3.0,
                                        label="Ratio de compresión (X:1)"
                                    )

                                gr.Markdown("#### ⚙️ Normalización")
                                with gr.Row():
                                    norm_input = gr.Checkbox(label="Normalizar entrada (RMS)", value=True)
                                    norm_output = gr.Checkbox(label="Normalizar salida (pico)", value=True)

                        def toggle_enhance_controls(enabled):
                            return gr.update(visible=enabled)

                        enhance_enabled.change(
                            fn=toggle_enhance_controls,
                            inputs=enhance_enabled,
                            outputs=enhance_controls_group
                        )

                        all_enhance_inputs = [
                            enhance_enabled, enhance_mode, enhance_strength,
                            enhance_highpass, enhance_lowpass,
                            voice_boost_db, voice_boost_low, voice_boost_high,
                            use_compressor, comp_threshold, comp_ratio,
                            norm_input, norm_output,
                        ]

                        def update_enhancement_config(
                            enabled, mode, strength,
                            highpass, lowpass,
                            boost_db, boost_low, boost_high,
                            compressor, comp_thr, comp_rat,
                            n_in, n_out
                        ):
                            transcription_service.set_enhancement_config({
                                'enabled': enabled,
                                'denoise_mode': mode,
                                'denoise_strength': float(strength),
                                'highpass_hz': int(highpass) if highpass else 0,
                                'lowpass_hz': int(lowpass) if lowpass else 0,
                                'voice_boost_db': float(boost_db),
                                'voice_boost_low_hz': int(boost_low),
                                'voice_boost_high_hz': int(boost_high),
                                'use_compressor': compressor,
                                'compressor_threshold_db': float(comp_thr),
                                'compressor_ratio': float(comp_rat),
                                'normalize_input': n_in,
                                'normalize_output': n_out,
                            })

                        for ctrl in all_enhance_inputs:
                            ctrl.change(
                                fn=update_enhancement_config,
                                inputs=all_enhance_inputs,
                                outputs=[]
                            )

                    # Panel derecho (Inferencia)
                    with gr.Column(scale=1):
                        gr.Markdown("### 📝 2. Transcribir Audio")

                        with gr.Group():
                            global_language = gr.Dropdown(
                                choices=["es"],
                                value="es",
                                label="🌐 Idioma del Audio",
                                info="Forzado a Español (es) para garantizar transcripciones correctas."
                            )

                        with gr.Tabs():
                            with gr.TabItem("Subir Archivo(s) Local(es)"):
                                with gr.Column():
                                    audio_input = gr.File(label="Sube tus Audios (WAV, MP3, M4A, OGG...)", file_types=["audio"], file_count="multiple")
                                    btn_transcribe = gr.Button("🎧 Transcribir Audio(s)", variant="primary", size="lg")

                            with gr.TabItem("Grabación de Micrófono"):
                                with gr.Column():
                                    mic_input = gr.Audio(sources=["microphone"], type="filepath", label="Micrófono")
                                    btn_mic_transcribe = gr.Button("🎤 Transcribir Micrófono", variant="primary", size="lg")

                            with gr.TabItem("Desde URL (YouTube/Podcast)"):
                                with gr.Column():
                                    url_input = gr.Textbox(label="Ingresa la URL del video/audio", placeholder="https://www.youtube.com/watch?v=...")
                                    btn_url_transcribe = gr.Button("🌐 Descargar y Transcribir", variant="primary", size="lg")

                        gr.Markdown("---")
                        transcript_output = gr.Textbox(
                            label="Vista Previa — Transcripción en tiempo real",
                            interactive=False,
                            lines=10,
                            elem_id="transcript-output",
                            placeholder="La transcripción aparecerá aquí mientras el modelo procesa el audio..."
                        )
                        gr.Markdown(
                            "_El audio se descarta apenas termina de procesarse — nunca queda "
                            "guardado, ni siquiera para reproducirlo aquí._",
                        )
                        metrics_display = gr.HTML(label="Métricas de Rendimiento", elem_id="metrics-display")

                        with gr.Group():
                            gr.Markdown("#### 🎓 Material de Estudio")
                            gr.Markdown(
                                "_Pensado para repasar o ponerte al día si faltaste a clase._",
                            )
                            btn_study_material = gr.Button(
                                "🎓 Generar Material de Estudio Completo", variant="primary", size="lg"
                            )
                            with gr.Row():
                                with gr.Column():
                                    gr.Markdown("**📋 Resumen de la Clase**")
                                    summary_output = gr.Markdown(
                                        value="_El resumen aparecerá aquí después de generarlo..._",
                                        container=True,
                                    )
                                with gr.Column():
                                    gr.Markdown("**🎯 Puntos Clave para Repasar**")
                                    key_points_output = gr.Markdown(
                                        value="_Los puntos clave aparecerán aquí después de generarlos..._",
                                        container=True,
                                    )
                            with gr.Row():
                                with gr.Column():
                                    gr.Markdown("**📖 Hoja de Repaso**")
                                    review_sheet_output = gr.Markdown(
                                        value="_La hoja de repaso aparecerá aquí después de generarla..._",
                                        container=True,
                                    )
                                with gr.Column():
                                    gr.Markdown("**🃏 Tarjetas de Estudio**")
                                    flashcards_output = gr.Markdown(
                                        value="_Las tarjetas de estudio aparecerán aquí después de generarlas..._",
                                        container=True,
                                    )

                        # Botones de exportación (Generando archivos locales)
                        with gr.Row():
                            download_txt = gr.File(label="Archivo(s) .TXT", interactive=False, file_count="multiple")
                            download_srt = gr.File(label="Archivo(s) .SRT", interactive=False, file_count="multiple")

            with gr.TabItem("🗄️ Historial"):
                with gr.Row():
                    with gr.Column(scale=2):
                        gr.Markdown("### 📜 Historial de Transcripciones")
                        btn_refresh = gr.Button("🔄 Actualizar Historial")
                        history_df = gr.Dataframe(headers=["ID", "Archivo", "Fecha", "Backend", "Texto"], interactive=False)

                    with gr.Column(scale=1):
                        gr.Markdown("### 📁 Archivos Físicos Generados")
                        gr.Markdown("Explora y descarga tus `.txt` y `.srt` directamente desde el servidor.")

                        # Crear el directorio base si no existe para que Gradio no falle
                        os.makedirs("outputs", exist_ok=True)
                        history_explorer = gr.FileExplorer(
                            root_dir="outputs",
                            label="Carpeta 'outputs'",
                            interactive=True
                        )
                        btn_refresh_files = gr.Button("🔄 Refrescar Archivos")

                def load_history():
                    rows = history_service.list_all()
                    return [[r["id"], r["filename"], r["date"], r["backend"], (r["text"][:100] + "...") if r["text"] else ""] for r in rows]

                btn_refresh.click(load_history, outputs=[history_df])
                btn_refresh_files.click(lambda: None, outputs=[history_explorer])  # Gradio actualiza al mandar un trigger
                app.load(load_history, outputs=[history_df])

            with gr.TabItem("⚙️ Configuración"):
                gr.Markdown("### Preferencias del Sistema")
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("#### Motor de Transcripción ASR")
                        cfg_beam_size = gr.Slider(minimum=1, maximum=10, step=1, label="Beam Size (Precisión vs Velocidad)", value=app_config.get_param("beam_size"))
                        cfg_vad = gr.Checkbox(label="Activar Filtro VAD (Voice Activity Detection)", value=app_config.get_param("vad_filter"))
                        cfg_compute_type = gr.Dropdown(choices=["default", "int8", "float16", "int8_float16"], label="Optimización de Computación (GPU/VRAM)", value=app_config.get_param("compute_type"))
                        cfg_language = gr.Dropdown(choices=["es"], label="Idioma Predeterminado", value="es")

                        gr.Markdown("#### Post-Procesamiento (Ollama LLM)")
                        cfg_ollama_model = gr.Textbox(
                            label="Modelo Ollama a utilizar",
                            value=app_config.get_param("ollama_model"),
                            placeholder="auto",
                            info="'auto' elige llama3.2:1b en CPU o llama3.2:3b si hay GPU disponible. También puedes poner un modelo explícito (ej. mistral, qwen)."
                        )
                        cfg_ollama_tokens = gr.Slider(minimum=256, maximum=8192, step=128, label="Máx. Tokens Resumen", value=int(app_config.get_param("ollama_max_tokens")))
                        cfg_ollama_chunk_chars = gr.Slider(
                            minimum=2000, maximum=16000, step=500,
                            label="Tamaño de bloque para clases largas (caracteres)",
                            info="Clases más largas que esto se parten en bloques y se condensan por separado antes de generar el material de estudio final, para no saturar la memoria ni exceder el contexto del modelo. Más chico = más seguro en hardware modesto, pero más llamadas a Ollama.",
                            value=int(app_config.get_param("ollama_chunk_chars"))
                        )

                        btn_save_cfg = gr.Button("💾 Guardar Preferencias", variant="primary")
                        cfg_status = gr.Textbox(label="Estado", interactive=False)

                        btn_save_cfg.click(
                            save_settings,
                            inputs=[cfg_beam_size, cfg_vad, cfg_compute_type, cfg_language, cfg_ollama_model, cfg_ollama_tokens, cfg_ollama_chunk_chars],
                            outputs=[cfg_status]
                        )

        btn_load_cloud.click(on_load_cloud, inputs=[cloud_dropdown], outputs=[status_box])
        btn_load_local.click(on_load_local, inputs=[local_path_input], outputs=[status_box])
        btn_transcribe.click(
            process_audio,
            inputs=[audio_input, global_language],
            outputs=[transcript_output, download_txt, download_srt, metrics_display]
        )
        btn_mic_transcribe.click(
            process_mic,
            inputs=[mic_input, global_language],
            outputs=[transcript_output, download_txt, download_srt, metrics_display]
        )
        btn_url_transcribe.click(
            process_url,
            inputs=[url_input, global_language],
            outputs=[transcript_output, download_txt, download_srt, metrics_display]
        )

        btn_study_material.click(
            on_generate_study_material,
            inputs=[transcript_output],
            outputs=[summary_output, key_points_output, review_sheet_output, flashcards_output]
        )

    return app
