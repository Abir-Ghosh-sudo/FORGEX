"""System and hardware information utilities for FORGEX."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SystemInfo:
    """Basic operating system information."""

    os_name: str
    os_version: str
    architecture: str
    machine: str
    processor: str
    python_version: str
    python_implementation: str


@dataclass(frozen=True, slots=True)
class HardwareInfo:
    """Hardware resource information."""

    cpu_count: int
    logical_cpu_count: int
    total_ram_bytes: int | None
    available_ram_bytes: int | None
    total_ram_gb: float | None
    available_ram_gb: float | None
    gpu_available: bool
    gpu_name: str | None


def _read_linux_memory() -> tuple[int | None, int | None]:
    """Read physical and available memory from Linux."""

    try:
        values: dict[str, int] = {}

        with open("/proc/meminfo", encoding="utf-8") as file:
            for line in file:
                key, _, remainder = line.partition(":")
                parts = remainder.split()

                if parts and key in {"MemTotal", "MemAvailable"}:
                    values[key] = int(parts[0]) * 1024

        return (
            values.get("MemTotal"),
            values.get("MemAvailable"),
        )
    except (OSError, ValueError, IndexError):
        return None, None


def _read_windows_memory() -> tuple[int | None, int | None]:
    """Read physical memory information on Windows."""

    try:
        import ctypes
        from ctypes import wintypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", wintypes.DWORD),
                ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)

        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(
            ctypes.byref(status)
        ):
            return None, None

        return (
            int(status.ullTotalPhys),
            int(status.ullAvailPhys),
        )

    except (AttributeError, OSError, TypeError, ValueError):
        return None, None


def _read_macos_memory() -> tuple[int | None, int | None]:
    """Read physical and available memory on macOS."""

    try:
        total_result = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        )

        total = int(total_result.stdout.strip())

        page_result = subprocess.run(
            ["vm_stat"],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        )

        page_size = 4096
        free_pages = 0

        for line in page_result.stdout.splitlines():
            if "page size of" in line:
                page_size = int(
                    line.split("page size of", 1)[1]
                    .split("bytes", 1)[0]
                    .strip()
                )

            if line.startswith(
                ("Pages free:", "Pages inactive:", "Pages speculative:")
            ):
                free_pages += int(
                    line.split(":", 1)[1]
                    .strip()
                    .rstrip(".")
                )

        return total, free_pages * page_size

    except (
        OSError,
        ValueError,
        subprocess.SubprocessError,
    ):
        return None, None


def get_memory_info() -> tuple[int | None, int | None]:
    """Return total and available physical memory in bytes."""

    system = platform.system()

    if system == "Windows":
        return _read_windows_memory()

    if system == "Linux":
        return _read_linux_memory()

    if system == "Darwin":
        return _read_macos_memory()

    return None, None


def detect_gpu() -> tuple[bool, str | None]:
    """Detect an NVIDIA GPU using the optional nvidia-smi utility."""

    executable = shutil.which("nvidia-smi")

    if executable is None:
        return False, None

    try:
        result = subprocess.run(
            [
                executable,
                "--query-gpu=name",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )

        names = [
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip()
        ]

        if names:
            return True, ", ".join(names)

    except subprocess.SubprocessError:
        pass

    return False, None


def get_system_info() -> SystemInfo:
    """Collect operating system and Python information."""

    return SystemInfo(
        os_name=platform.system(),
        os_version=platform.version(),
        architecture=platform.architecture()[0],
        machine=platform.machine(),
        processor=platform.processor() or "Unknown",
        python_version=platform.python_version(),
        python_implementation=platform.python_implementation(),
    )


def get_hardware_info() -> HardwareInfo:
    """Collect CPU, RAM, and GPU information."""

    cpu_count = os.cpu_count() or 1
    total_memory, available_memory = get_memory_info()
    gpu_available, gpu_name = detect_gpu()

    to_gb = 1024 ** 3

    return HardwareInfo(
        cpu_count=cpu_count,
        logical_cpu_count=cpu_count,
        total_ram_bytes=total_memory,
        available_ram_bytes=available_memory,
        total_ram_gb=(
            round(total_memory / to_gb, 2)
            if total_memory is not None
            else None
        ),
        available_ram_gb=(
            round(available_memory / to_gb, 2)
            if available_memory is not None
            else None
        ),
        gpu_available=gpu_available,
        gpu_name=gpu_name,
    )


def get_system_report() -> dict[str, Any]:
    """Return a JSON-serializable system and hardware report."""

    return {
        "system": asdict(get_system_info()),
        "hardware": asdict(get_hardware_info()),
    }


__all__ = [
    "SystemInfo",
    "HardwareInfo",
    "get_memory_info",
    "detect_gpu",
    "get_system_info",
    "get_hardware_info",
    "get_system_report",
]