# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

import torch


def detect_gpu_vendor() -> str:
    """'nvidia' | 'amd' | 'none'. Un PyTorch-ROCm hace que
    torch.cuda.is_available() devuelva True también para GPU AMD, así que
    se distingue por torch.version.hip (solo existe en builds ROCm)."""
    if not torch.cuda.is_available():
        return "none"
    return "amd" if getattr(torch.version, "hip", None) is not None else "nvidia"
