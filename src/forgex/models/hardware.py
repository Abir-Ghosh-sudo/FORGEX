"""Hardware-aware heuristics for local model selection."""

from __future__ import annotations

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
    """Detect local hardware and derive safe local-model defaults."""
    system = platform.system()
    machine = platform.machine()
    cpu_count = os.cpu_count() or 1
    total_memory_gb = _detect_total_memory_gb()
    gpu_available, gpu_name, vram_gb = _detect_gpu()

    mem = total_memory_gb or 8.0
    if mem <= 8:
        ctx = 4096
        quant = "Q4_K_M"
    elif mem <= 16:
        ctx = 8192
        quant = "Q4_K_M"
    elif mem <= 32:
        ctx = 16384
        quant = "Q5_K_M"
    else:
        ctx = 32768
        quant = "Q6_K"

    if vram_gb is not None and vram_gb >= 8:
        ctx = max(ctx, 16384)
        quant = "Q5_K_M" if vram_gb < 12 else "Q6_K"

    if gpu_available and shutil.which("ollama"):
        preferred = "ollama"
    elif shutil.which("ollama"):
        preferred = "ollama"
    elif _python_package_available("llama_cpp"):
        preferred = "llama_cpp"
    elif _python_package_available("transformers"):
        preferred = "transformers"
    else:
        preferred = "ollama"

    sequential = mem <= 16

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
        sequential_agents_recommended=sequential,
    )


def _detect_total_memory_gb() -> float | None:
    try:
        import psutil  # type: ignore

        return round(psutil.virtual_memory().total / (1024**3), 2)
    except Exception:
        pass

    try:
        if platform.system() == "Windows":
            result = subprocess.run(
                ["wmic", "computersystem", "get", "TotalPhysicalMemory", "/value"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            for line in result.stdout.splitlines():
                if "TotalPhysicalMemory" in line and "=" in line:
                    value = line.split("=", 1)[1].strip()
                    if value:
                        return round(int(value) / (1024**3), 2)
        elif Path("/proc/meminfo").exists():
            for line in Path("/proc/meminfo").read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return round(kb / (1024**2), 2)
    except Exception:
        logger.debug("Total memory detection failed.", exc_info=True)
    return None


def _detect_gpu() -> tuple[bool, str | None, float | None]:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            line = result.stdout.strip().splitlines()[0]
            parts = [p.strip() for p in line.split(",")]
            name = parts[0] if parts else None
            vram = None
            if len(parts) > 1:
                try:
                    vram = round(float(parts[1]) / 1024.0, 2)
                except Exception:
                    vram = None
            return True, name, vram
    except Exception:
        logger.debug("GPU detection failed.", exc_info=True)
    return False, None, None


def _python_package_available(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except Exception:
        return False


__all__ = ["HardwareProfile", "detect_hardware"]
