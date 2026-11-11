"""Native C++ engine bindings for FORGEX."""

from __future__ import annotations

import importlib
import logging
from functools import lru_cache
from types import ModuleType
from typing import Any

logger = logging.getLogger(__name__)

NATIVE_MODULE = "forgex._native"


class NativeEngineError(RuntimeError):
    """Raised when native engine operations fail."""


@lru_cache(maxsize=1)
def load_native_engine() -> ModuleType | None:
    """Load the compiled native extension if available."""
    try:
        module = importlib.import_module(NATIVE_MODULE)
    except (ImportError, OSError) as exc:
        logger.debug("Native engine unavailable: %s", exc)
        return None

    return module


def is_native_available() -> bool:
    """Check whether the native extension is available."""
    return load_native_engine() is not None


def get_native_function(name: str) -> Any:
    """Retrieve a function exposed by the native extension."""
    if not name or not isinstance(name, str):
        raise ValueError("Function name must be a non-empty string.")

    module = load_native_engine()

    if module is None:
        raise NativeEngineError(
            "Native extension is unavailable. "
            "Build the C++ engine or use the Python fallback."
        )

    function = getattr(module, name, None)

    if not callable(function):
        raise NativeEngineError(
            f"Native function '{name}' is not available."
        )

    return function


def native_capabilities() -> dict[str, Any]:
    """Return native engine capabilities."""
    module = load_native_engine()

    if module is None:
        return {
            "available": False,
            "module": NATIVE_MODULE,
            "functions": [],
        }

    functions = sorted(
        name
        for name in dir(module)
        if not name.startswith("_")
        and callable(getattr(module, name, None))
    )

    return {
        "available": True,
        "module": NATIVE_MODULE,
        "version": getattr(module, "__version__", "unknown"),
        "functions": functions,
    }


def clear_native_cache() -> None:
    """Clear cached native module loading state."""
    load_native_engine.cache_clear()