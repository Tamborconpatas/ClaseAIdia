# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Los modelos de texto que elige la aplicación, en un solo lugar y sin importar PyTorch: el servidor web los necesita
para ofrecer la descarga y avisar si falta uno, y no debe cargar `infraestructura.hardware` (que importa torch)."""

MODELO_CPU = "gemma4:e2b"  # el de `auto` sin GPU (QA.md, «Clase completa en solo CPU»: ~9 min para una clase de 62 min, 4,6 GB)
MODELO_GPU = "llama3.2:3b"  # el de `auto` con GPU
MODELO_MINIMO = "llama3.2:1b"  # solo si no hay memoria libre para los otros (sin mapa conceptual)
TAMANO_GB = {MODELO_CPU: 4.6, MODELO_GPU: 2.0, MODELO_MINIMO: 1.3}  # lo que se descarga (`ollama list`); otros modelos: no se sabe
MEMORIA_MINIMA_GB = 12.0  # RAM del equipo para el modelo por defecto más el sistema (QA.md, «Memoria de todo el proyecto»)


def modelo_a_instalar(configurado: str) -> str:
    """El modelo que el UTP debe bajar: el que fijó quien administra el servidor, o el de CPU si está en `auto`. Un equipo con GPU en
    `auto` usa `MODELO_GPU` (lo decide `servicio_material_estudio`, que sí puede mirar la GPU)."""
    return MODELO_CPU if configurado == "auto" else configurado
