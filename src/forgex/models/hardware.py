"""Hardware-aware heuristics without importing heavyweight ML runtimes."""

from __future__ import annotations

import contextlib
import importlib.util
import logging
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class HardwareProfile:
    """Detected machine capabilities relevant to local inference."""

    system: str
    machine: str
    cpu_count: int
    total_memory_gb: float | None
    gpu_available: bool
    gpu_name: str | None
    vram_gb: float | None
    recommended_context_window: int
    recommended_quantization: str
    preferred_provider: str
    sequential_agents_recommended: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "system": self.system,
            "machine": self.machine,
            "cpu_count": self.cpu_count,
            "total_memory_gb": self.total_memory_gb,
            "gpu_available": self.gpu_available,
            "gpu_name": self.gpu_name,
            "vram_gb": self.vram_gb,
            "recommended_context_window": self.recommended_context_window,
            "recommended_quantization": self.recommended_quantization,
            "preferred_provider": self.preferred_provider,
            "sequential_agents_recommended": self.sequential_agents_recommended,
        }


def detect_hardware() -> HardwareProfile:
    """Detect hardware using lightweight OS queries only."""
    system = platform.system()
    machine = platform.machine()
    cpu_count = os.cpu_count() or 1
    total_memory_gb = _detect_total_memory_gb()
    gpu_available, gpu_name, vram_gb = _detect_gpu()

    mem = total_memory_gb or 8.0
    if mem <= 8:
        ctx, quant = 2048, "Q4_K_M"
    elif mem <= 16:
        ctx, quant = 4096, "Q4_K_M"
    elif mem <= 32:
        ctx, quant = 8192, "Q4_K_M"
    else:
        ctx, quant = 16384, "Q5_K_M"

    if vram_gb is not None and vram_gb >= 8:
        ctx = max(ctx, 8192)
        quant = "Q5_K_M" if vram_gb < 12 else "Q6_K"

    if shutil.which("ollama"):
        preferred = "ollama"
    elif _module_available("llama_cpp"):
        preferred = "llama_cpp"
    elif _module_available("transformers"):
        preferred = "transformers"
    else:
        preferred = "ollama"

    return HardwareProfile(
        system=system,
        machine=machine,
        cpu_count=cpu_count,
        total_memory_gb=total_memory_gb,
        gpu_available=gpu_available,
        gpu_name=gpu_name,
        vram_gb=vram_gb,
        recommended_context_window=ctx,
        recommended_quantization=quant,
        preferred_provider=preferred,
        sequential_agents_recommended=mem <= 16,
    )


def _detect_total_memory_gb() -> float | None:
    try:
        import psutil  # type: ignore

        return round(psutil.virtual_memory().total / (1024**3), 2)
    except Exception:
        pass

    try:
        if platform.system() == "Windows":
            import ctypes

            class MemoryStatusEx(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MemoryStatusEx()
            stat.dwLength = ctypes.sizeof(MemoryStatusEx)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return round(stat.ullTotalPhys / (1024**3), 2)
        elif Path("/proc/meminfo").exists():
            for line in (
                Path("/proc/meminfo").read_text(encoding="utf-8", errors="ignore").splitlines()
            ):
                if line.startswith("MemTotal:"):
                    return round(int(line.split()[1]) / (1024**2), 2)
    except Exception:
        logger.debug("Total memory detection failed.", exc_info=True)
    return None


def _detect_gpu() -> tuple[bool, str | None, float | None]:
    """Detect NVIDIA GPUs without importing a machine-learning framework."""
    executable = shutil.which("nvidia-smi")
    if not executable:
        return False, None, None

    try:
        result = subprocess.run(
            [
                executable,
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = [part.strip() for part in result.stdout.strip().splitlines()[0].split(",")]
            name = parts[0] if parts else None
            vram = None
            if len(parts) > 1:
                with contextlib.suppress(ValueError):
                    vram = round(float(parts[1]) / 1024.0, 2)
            return True, name, vram
    except Exception:
        logger.debug("GPU detection failed.", exc_info=True)
    return False, None, None


def _module_available(module_name: str) -> bool:
    """Check optional dependency presence without importing it."""
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False


__all__ = ["HardwareProfile", "detect_hardware"]
