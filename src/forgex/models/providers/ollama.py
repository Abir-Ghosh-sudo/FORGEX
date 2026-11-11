"""Ollama local inference provider for FORGEX."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from typing import Any
from urllib import error, request

from forgex.models.base import (
    BaseModelProvider,
    GenerationResult,
    ModelCapabilities,
    ModelMessage,
    ModelProviderInfo,
)
from forgex.models.errors import ModelInferenceError, ModelNotFoundError

logger = logging.getLogger(__name__)


class OllamaProvider(BaseModelProvider):
    """Local model inference via Ollama (HTTP API with CLI fallback)."""

    provider_name = "ollama"

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11434",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.base_url = (base_url or "http://127.0.0.1:11434").rstrip("/")

    @property
    def info(self) -> ModelProviderInfo:
        return ModelProviderInfo(
            name="ollama",
            display_name="Ollama",
            local=True,
            supports_download=False,
            description="Local model inference through Ollama runtime.",
        )

    @property
    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(
            streaming=False,
            tool_calling=False,
            json_mode=True,
            max_context_tokens=self.context_window,
            local_only=True,
        )

    def _generate_sync(
        self,
        messages: list[ModelMessage],
        **kwargs: Any,
    ) -> GenerationResult:
        payload = {
            "model": self.model_name,
            "messages": [m.to_dict() for m in messages],
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", self.temperature),
                "top_p": kwargs.get("top_p", self.top_p),
                "num_predict": kwargs.get("max_output_tokens", self.max_output_tokens),
                "num_ctx": kwargs.get("context_window", self.context_window),
            },
        }

        try:
            data = self._chat_http(payload)
            message = data.get("message") or {}
            text = str(message.get("content", ""))
            return GenerationResult(
                text=text,
                model=str(data.get("model", self.model_name)),
                provider=self.provider_name,
                finish_reason=str(data.get("done_reason", "stop"))
                if data.get("done_reason")
                else "stop",
                prompt_tokens=self._safe_int(data.get("prompt_eval_count")),
                completion_tokens=self._safe_int(data.get("eval_count")),
                total_tokens=self._safe_total(data),
                raw=data,
            )
        except ModelNotFoundError:
            raise
        except Exception as http_exc:
            logger.debug("Ollama HTTP generation failed, trying CLI: %s", http_exc)

        try:
            return self._chat_cli(messages, **kwargs)
        except Exception as cli_exc:
            raise ModelInferenceError(
                f"Ollama inference failed for '{self.model_name}': {cli_exc}",
                provider=self.provider_name,
            ) from cli_exc

    def _chat_http(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url=f"{self.base_url}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.request_timeout_seconds) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw) if raw else {}
        except error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:
                detail = str(exc)
            lower = detail.lower()
            if exc.code == 404 or "not found" in lower or "model" in lower:
                raise ModelNotFoundError(
                    f"Ollama model not found: {self.model_name}",
                    provider=self.provider_name,
                    model=self.model_name,
                ) from exc
            raise ModelInferenceError(
                f"Ollama HTTP error {exc.code}: {detail or exc.reason}",
                provider=self.provider_name,
            ) from exc
        except error.URLError as exc:
            raise ModelInferenceError(
                f"Cannot reach Ollama at {self.base_url}: {exc}",
                provider=self.provider_name,
            ) from exc

    def _chat_cli(
        self,
        messages: list[ModelMessage],
        **kwargs: Any,
    ) -> GenerationResult:
        executable = shutil.which("ollama")
        if not executable:
            raise ModelInferenceError(
                "Ollama CLI not found in PATH.",
                provider=self.provider_name,
            )
        prompt = self._messages_to_prompt(messages)
        proc = subprocess.run(
            [executable, "run", self.model_name, prompt],
            capture_output=True,
            text=True,
            timeout=max(10, int(self.request_timeout_seconds)),
            check=False,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "Unknown Ollama error").strip()
            if "not found" in err.lower():
                raise ModelNotFoundError(
                    f"Ollama model not found: {self.model_name}",
                    provider=self.provider_name,
                    model=self.model_name,
                )
            raise ModelInferenceError(err, provider=self.provider_name)
        return GenerationResult(
            text=(proc.stdout or "").strip(),
            model=self.model_name,
            provider=self.provider_name,
            finish_reason="stop",
            raw={"stdout": proc.stdout, "stderr": proc.stderr},
        )

    @staticmethod
    def _messages_to_prompt(messages: list[ModelMessage]) -> str:
        parts: list[str] = []
        for msg in messages:
            role = msg.role.upper()
            parts.append(f"{role}:\n{msg.content}")
        parts.append("ASSISTANT:")
        return "\n\n".join(parts)

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            if value is None:
                return None
            return int(value)
        except Exception:
            return None

    @staticmethod
    def _safe_total(data: dict[str, Any]) -> int | None:
        p = OllamaProvider._safe_int(data.get("prompt_eval_count"))
        c = OllamaProvider._safe_int(data.get("eval_count"))
        if p is None or c is None:
            return None
        return p + c

    def is_available(self) -> bool:
        try:
            req = request.Request(url=f"{self.base_url}/api/tags", method="GET")
            with request.urlopen(req, timeout=3) as resp:
                return 200 <= resp.status < 300
        except Exception:
            return shutil.which("ollama") is not None

    @staticmethod
    def list_local_models(base_url: str = "http://127.0.0.1:11434") -> list[str]:
        base_url = (base_url or "http://127.0.0.1:11434").rstrip("/")
        try:
            req = request.Request(url=f"{base_url}/api/tags", method="GET")
            with request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace") or "{}")
            models = data.get("models") or []
            names = []
            for item in models:
                if isinstance(item, dict) and item.get("name"):
                    names.append(str(item["name"]))
            if names:
                return names
        except Exception:
            pass

        executable = shutil.which("ollama")
        if not executable:
            raise ModelInferenceError(
                "Ollama is not available (API unreachable and CLI not found).",
                provider="ollama",
            )
        proc = subprocess.run(
            [executable, "list"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if proc.returncode != 0:
            raise ModelInferenceError(
                (proc.stderr or "Failed to list Ollama models").strip(),
                provider="ollama",
            )
        names = []
        for line in (proc.stdout or "").splitlines()[1:]:
            parts = line.split()
            if parts:
                names.append(parts[0])
        return names

    @staticmethod
    def pull_model(
        model_name: str,
        base_url: str = "http://127.0.0.1:11434",
    ) -> tuple[bool, str]:
        name = (model_name or "").strip()
        if not name:
            return False, "Model name cannot be empty."
        executable = shutil.which("ollama")
        if not executable:
            return False, "Ollama CLI not found in PATH."
        proc = subprocess.run(
            [executable, "pull", name],
            capture_output=True,
            text=True,
            timeout=3600,
            check=False,
        )
        output = (proc.stdout or proc.stderr or "").strip()
        if proc.returncode != 0:
            return False, output or "Ollama pull failed."
        return True, output or f"Pulled {name}."


__all__ = ["OllamaProvider"]
