import torch


def detect_gpu_vendor() -> str:
    """'nvidia' | 'amd' | 'none'. Un PyTorch-ROCm hace que
    torch.cuda.is_available() devuelva True también para GPU AMD, así que
    se distingue por torch.version.hip (solo existe en builds ROCm)."""
    if not torch.cuda.is_available():
        return "none"
    return "amd" if getattr(torch.version, "hip", None) is not None else "nvidia"
