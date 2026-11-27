"""Unit tests for FORGEX models layer."""

from __future__ import annotations

import pytest

from forgex.models.base import ModelMessage, GenerationResult, StreamChunk
from forgex.models.context_budget import ContextBudgeter
from forgex.models.errors import ModelConfigurationError, ModelNotFoundError
from forgex.models.hardware import detect_hardware
from forgex.models.router import ModelRoute, ModelRouter
from forgex.models.providers.openai_compatible import OpenAICompatibleProvider
from forgex.config.settings import ModelSettings


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



def test_openai_compatible_provider_parses_complete_generation_result():
    provider = OpenAICompatibleProvider(model_name="test-model")
    result = provider._parse_response(
        {
            "choices": [
                {
                    "message": {"content": "hello"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 4,
                "completion_tokens": 2,
                "total_tokens": 6,
            },
        }
    )

    assert result.text == "hello"
    assert result.model == "test-model"
    assert result.provider == "openai_compatible"
    assert result.total_tokens == 6


def test_openai_compatible_provider_declares_valid_capabilities():
    provider = OpenAICompatibleProvider(model_name="test-model")
    capabilities = provider.capabilities

    assert capabilities.streaming is True
    assert capabilities.tool_calling is True
    assert capabilities.local_only is False


def test_cloud_model_provider_can_be_configured():
    settings = ModelSettings(
        provider="openai_compatible",
        model_name="test-model",
        openai_base_url="https://router.huggingface.co/v1",
        openai_api_key="test-token",
    )

    assert settings.provider == "openai_compatible"
    assert settings.openai_api_key == "test-token"


def test_low_resource_model_defaults_are_safe_for_laptops():
    settings = ModelSettings()

    assert settings.model_name == "qwen2.5-coder:1.5b"
    assert settings.context_window == 4096
    assert settings.max_output_tokens == 1024
    assert settings.ollama_num_threads == 4


def test_ollama_provider_applies_resource_limits(monkeypatch):
    from forgex.models.providers.ollama import OllamaProvider

    provider = OllamaProvider(
        model_name="test-model",
        num_threads=2,
        keep_alive="1m",
    )
    captured = {}

    def fake_chat(payload):
        captured.update(payload)
        return {
            "model": "test-model",
            "message": {"content": "ok"},
            "eval_count": 1,
            "prompt_eval_count": 1,
        }

    monkeypatch.setattr(provider, "_chat_http", fake_chat)
    result = provider._generate_sync([ModelMessage(role="user", content="hi")])

    assert result.text == "ok"
    assert captured["keep_alive"] == "1m"
    assert captured["options"]["num_thread"] == 2
    assert captured["options"]["num_ctx"] == 8192
    assert captured["options"]["num_batch"] == 128


def test_hardware_module_probe_does_not_import_ml_runtime(monkeypatch):
    from forgex.models import hardware

    calls = []

    def fake_find_spec(name):
        calls.append(name)
        return None

    monkeypatch.setattr(hardware.importlib.util, "find_spec", fake_find_spec)

    assert hardware._module_available("transformers") is False
    assert calls == ["transformers"]


def test_model_router_checks_optional_packages_without_importing(monkeypatch):
    import importlib.util

    from forgex.models.router import ModelRouter

    checked = []

    def fake_find_spec(name):
        checked.append(name)
        return None

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)

    assert ModelRouter._module_available("transformers") is False
    assert checked == ["transformers"]



def test_ollama_missing_model_error_includes_recovery_steps(monkeypatch):
    import asyncio
    from urllib.error import HTTPError
    from io import BytesIO

    from forgex.models.providers.ollama import OllamaProvider

    provider = OllamaProvider(model_name="qwen2.5-coder:1.5b")
    body = BytesIO(b'{"error":"model not found"}')

    def missing_model(*args, **kwargs):
        raise HTTPError(
            url="http://127.0.0.1:11434/api/chat",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=body,
        )

    monkeypatch.setattr(
        "forgex.models.providers.ollama.request.urlopen",
        missing_model,
    )

    with pytest.raises(ModelNotFoundError) as exc:
        provider._chat_http({"model": provider.model_name})

    assert "forgex model pull qwen2.5-coder:1.5b" in str(exc.value)
    assert "forgex model list" in str(exc.value)


def test_async_provider_keeps_model_not_found_error(monkeypatch):
    import asyncio

    from forgex.models.providers.ollama import OllamaProvider

    provider = OllamaProvider(model_name="missing-model")

    def raise_missing_model(*args, **kwargs):
        raise ModelNotFoundError(
            "Model is not installed.",
            provider="ollama",
            model="missing-model",
        )

    monkeypatch.setattr(provider, "_generate_sync", raise_missing_model)

    with pytest.raises(ModelNotFoundError, match="not installed"):
        asyncio.run(
            provider.generate_async([{"role": "user", "content": "hello"}])
        )
