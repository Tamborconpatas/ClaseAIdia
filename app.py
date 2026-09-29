import os

# Debe fijarse ANTES de cualquier import que arrastre torch.
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True,max_split_size_mb:128"

from nucleo.configuracion import cargar_env

cargar_env()

from interfaz.app_gradio import create_ui

if __name__ == "__main__":
    demo_app = create_ui()
    print("=======[ Universal Local Transcriber Iniciando ]=======")
    # 0.0.0.0 en Docker para que el puerto publicado del contenedor funcione.
    server_name = os.environ.get("SERVER_NAME", "127.0.0.1")
    server_port = int(os.environ.get("SERVER_PORT", "7862"))
    demo_app.launch(server_name=server_name, server_port=server_port, share=False)
