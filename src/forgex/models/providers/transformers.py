"""Transformers local inference provider for FORGEX."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from forgex.models.base import (
    BaseModelProvider,
    GenerationResult,
    ModelCapabilities,
    ModelMessage,
    ModelProviderInfo,
)
from forgex.models.errors import ModelInferenceError, ModelNotFoundError

logger = logging.getLogger(__name__)


class TransformersProvider(BaseModelProvider):
    """Local inference via Hugging Face Transformers.

    Uses locally available model files/directories. Can load from a local
    path or a cached/downloaded Hugging Face repo when local files exist.
    """

    provider_name = "transformers"

    def __init__(
        self,
        *,
        trust_remote_code: bool = False,
        local_files_only: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.trust_remote_code = trust_remote_code
        self.local_files_only = local_files_only
        self._pipeline: Any = None
        self._model_id: str | None = None

    @property
    def info(self) -> ModelProviderInfo:
        return ModelProviderInfo(
            name="transformers",
            display_name="Transformers",
            local=True,
            supports_download=True,
            description="Local inference using Hugging Face Transformers.",
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

    def _resolve_model_id(self) -> str:
        if self.model_path:
            path = Path(self.model_path).expanduser().resolve()
            if not path.exists():
                raise ModelNotFoundError(
                    f"Transformers model path not found: {path}",
                    provider=self.provider_name,
                    model=str(path),
                )
            return str(path)
        return self.model_name

    def _load(self) -> Any:
        if self._pipeline is not None:
            return self._pipeline

        try:
            from transformers import pipeline  # type: ignore
        except Exception as exc:
            raise ModelInferenceError(
                "transformers is not installed.",
                provider=self.provider_name,
            ) from exc

        model_id = self._resolve_model_id()
        self._model_id = model_id

        if self.local_files_only:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

        device_map = "cpu"
        try:
            import torch  # type: ignore

            if torch.cuda.is_available():
                device_map = "auto"
        except Exception:
            pass

        last_exc: Exception | None = None
        for task in ("text-generation", None):
            try:
                kwargs: dict[str, Any] = {
                    "model": model_id,
                    "trust_remote_code": self.trust_remote_code,
                    "device_map": device_map,
                }
                if task:
                    kwargs["task"] = task
                try:
                    self._pipeline = pipeline(**kwargs)
                except TypeError:
                    kwargs.pop("device_map", None)
                    self._pipeline = pipeline(**kwargs)
                return self._pipeline
            except Exception as exc:
                last_exc = exc

        raise ModelInferenceError(
            f"Failed to load Transformers model '{model_id}': {last_exc}",
            provider=self.provider_name,
        ) from last_exc

    def _generate_sync(
        self,
        messages: list[ModelMessage],
        **kwargs: Any,
    ) -> GenerationResult:
        pipe = self._load()
        max_new = int(kwargs.get("max_output_tokens", self.max_output_tokens))
        temperature = float(kwargs.get("temperature", self.temperature))
        top_p = float(kwargs.get("top_p", self.top_p))
        do_sample = temperature > 0

        gen_kwargs: dict[str, Any] = {
            "max_new_tokens": max_new,
            "do_sample": do_sample,
            "temperature": temperature if do_sample else None,
            "top_p": top_p if do_sample else None,
            "return_full_text": False,
        }
        gen_kwargs = {k: v for k, v in gen_kwargs.items() if v is not None}

        try:
            try:
                output = pipe([m.to_dict() for m in messages], **gen_kwargs)
            except Exception:
                prompt = self._messages_to_prompt(messages)
                output = pipe(prompt, **gen_kwargs)
        except Exception as exc:
            raise ModelInferenceError(
                f"Transformers inference failed: {exc}",
                provider=self.provider_name,
            ) from exc

        text = self._extract_text(output)
        return GenerationResult(
            text=text,
            model=self._model_id or self.model_name,
            provider=self.provider_name,
            finish_reason="stop",
            raw=output,
        )

    @staticmethod
    def _extract_text(output: Any) -> str:
        if isinstance(output, str):
            return output
        if isinstance(output, list) and output:
            item = output[0]
            if isinstance(item, dict):
                if "generated_text" in item:
                    gt = item["generated_text"]
                    if isinstance(gt, str):
                        return gt
                    if isinstance(gt, list) and gt:
                        last = gt[-1]
                        if isinstance(last, dict):
                            return str(last.get("content", ""))
                        return str(last)
                    return str(gt)
                if "text" in item:
                    return str(item["text"])
            return str(item)
        if isinstance(output, dict):
            return str(output.get("generated_text") or output.get("text") or output)
        return str(output)

    @staticmethod
    def _messages_to_prompt(messages: list[ModelMessage]) -> str:
        parts = [f"{m.role.upper()}:\n{m.content}" for m in messages]
        parts.append("ASSISTANT:")
        return "\n\n".join(parts)

    def is_available(self) -> bool:
        try:
            import transformers  # noqa: F401

            if self.model_path:
                return Path(self.model_path).expanduser().resolve().exists()
            return True
        except Exception:
            return False

    def close(self) -> None:
        self._pipeline = None
        super().close()


__all__ = ["TransformersProvider"]
