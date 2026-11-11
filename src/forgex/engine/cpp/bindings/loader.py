"""Safe native engine loader."""

from __future__ import annotations

import importlib
import logging
from types import ModuleType
from typing import Any

logger = logging.getLogger(__name__)

_MODULE_NAME = "forgex._native"

_native_module: ModuleType | None = None
_load_attempted = False


def load_native() -> ModuleType | None:
    """Load the compiled native extension once."""

    global _native_module, _load_attempted

    if _load_attempted:
        return _native_module

    _load_attempted = True

    try:
        _native_module = importlib.import_module(_MODULE_NAME)

        logger.info("FORGEX native engine loaded successfully")

    except ImportError as exc:
        _native_module = None

        logger.debug(
            "Native engine unavailable: %s",
            exc,
        )

    return _native_module


def is_native_available() -> bool:
    return load_native() is not None


def get_native_function(name: str) -> Any | None:
    """Get a native function or class by name."""

    if not name or not isinstance(name, str):
        raise ValueError("Native function name must be a non-empty string")

    module = load_native()

    if module is None:
        return None

    return getattr(module, name, None)


def native_capabilities() -> dict[str, bool]:
    module = load_native()

    if module is None:
        return {}

    function = getattr(module, "native_capabilities", None)

    if function is None:
        return {}

    return dict(function())


def reset_native_loader() -> None:
    """Reset loader state. Mainly useful for tests."""

    global _native_module, _load_attempted

    _native_module = None
    _load_attempted = False
