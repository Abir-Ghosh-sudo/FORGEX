"""Unit tests for FORGEX native C++ engine and Python fallback."""

from __future__ import annotations

import pytest

from forgex.engine.bindings import (
    is_native_available,
    load_native_engine,
)


class TestNativeEngine:
    """Verify native engine acceleration and capability reporting."""

    def test_native_availability(self) -> None:
        """Check native engine detection."""
        available = is_native_available()
        assert isinstance(available, bool)

    def test_load_native_engine(self) -> None:
        """Verify module loading returns a valid module or None fallback."""
        module = load_native_engine()
        if is_native_available():
            assert module is not None
            assert hasattr(module, "native_capabilities")
            caps = module.native_capabilities()
            assert isinstance(caps, dict)
            assert caps.get("core") is True
            assert caps.get("parser") is True
            assert caps.get("search") is True
            assert caps.get("indexing") is True
        else:
            pytest.skip("Native engine binary not available on this platform.")

    def test_native_capabilities_values(self) -> None:
        """Verify native capabilities keys when module is present."""
        module = load_native_engine()
        if module is None:
            pytest.skip("Native engine binary not available.")

        capabilities = module.native_capabilities()
        expected_keys = {"core", "parser", "search", "indexing", "persistent_index"}
        assert expected_keys.issubset(capabilities.keys())
        for key in expected_keys:
            assert capabilities[key] is True
