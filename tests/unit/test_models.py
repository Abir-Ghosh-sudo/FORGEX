"""Unit tests for FORGEX models layer."""

from __future__ import annotations

import pytest

from forgex.models.base import ModelMessage, GenerationResult, StreamChunk
from forgex.models.context_budget import ContextBudgeter
from forgex.models.errors import ModelConfigurationError, ModelNotFoundError
from forgex.models.hardware import detect_hardware
from forgex.models.router import ModelRoute, ModelRouter


class TestModelMessage:
    def test_from_mapping(self):
        msg = ModelMessage.from_mapping({"role": "user", "content": "hello"})
        assert msg.role == "user"
        assert msg.content == "hello"

    def test_to_dict(self):
        msg = ModelMessage(role="system", content="sys")
        d = msg.to_dict()
        assert d == {"role": "system", "content": "sys"}


class TestGenerationResult:
    def test_to_dict(self):
        r = GenerationResult(text="hi", model="m", provider="p")
        d = r.to_dict()
        assert d["text"] == "hi"
        assert d["model"] == "m"
        assert d["provider"] == "p"


class TestContextBudgeter:
    def test_fit_messages_empty(self):
        b = ContextBudgeter(context_window=4096)
        msgs, budget = b.fit_messages([])
        assert msgs == []
        assert budget.fits is True

    def test_fit_messages_fits(self):
        b = ContextBudgeter(context_window=4096)
        msgs = [
            {"role": "system", "content": "You are a coder."},
            {"role": "user", "content": "Hello world"},
        ]
        fitted, budget = b.fit_messages(msgs)
        assert budget.fits is True
        assert len(fitted) == 2


class TestHardware:
    def test_detect_hardware(self):
        hw = detect_hardware()
        assert hw.system in {"Windows", "Linux", "Darwin"}
        assert hw.cpu_count >= 1
        assert hw.preferred_provider in {"ollama", "llama_cpp", "transformers"}


class TestModelRouter:
    def test_validate_provider(self):
        router = ModelRouter()
        with pytest.raises(Exception):
            router._validate_provider("invalid")

    def test_normalize_provider(self):
        assert ModelRouter._normalize_provider("llama.cpp") == "llama_cpp"
        assert ModelRouter._normalize_provider("hf") == "transformers"


class TestErrors:
    def test_model_configuration_error(self):
        with pytest.raises(ModelConfigurationError):
            raise ModelConfigurationError("bad config")

    def test_model_not_found(self):
        with pytest.raises(ModelNotFoundError) as exc:
            raise ModelNotFoundError("not found", model="x")
        assert exc.value.model == "x"
