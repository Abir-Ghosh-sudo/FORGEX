"""FORGEX native performance engine.

Provides optional C++ acceleration with pure Python fallbacks.
"""

from __future__ import annotations

try:
    from forgex.engine.bindings import (
        is_native_available,
        load_native_engine,
    )
except ImportError:
    def is_native_available() -> bool:
        """Return whether native acceleration is available."""
        return False

    def load_native_engine():
        """Return None when the native extension is unavailable."""
        return None


__all__ = [
    "is_native_available",
    "load_native_engine",
]