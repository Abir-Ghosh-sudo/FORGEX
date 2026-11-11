"""FORGEX local model management and inference.

Provides Hugging Face Hub weight downloading, local inference providers
(Ollama, llama.cpp, Transformers), hardware-aware routing, context
budgeting, and a unified generation interface for agents.
"""

from forgex.models.base import (
    BaseModelProvider,
    GenerationResult,
    ModelCapabilities,
    ModelMessage,
    ModelProviderInfo,
    StreamChunk,
)
from forgex.models.context_budget import ContextBudget, ContextBudgeter
from forgex.models.downloader import (
    DownloadResult,
    HuggingFaceDownloadError,
    HuggingFaceDownloader,
)
from forgex.models.errors import (
    ModelConfigurationError,
    ModelDownloadError,
    ModelInferenceError,
    ModelNotFoundError,
    ModelProviderError,
    ModelRoutingError,
)
from forgex.models.hardware import HardwareProfile, detect_hardware
from forgex.models.manager import ModelManager
from forgex.models.router import ModelRoute, ModelRouter

__all__ = [
    "BaseModelProvider",
    "GenerationResult",
    "ModelCapabilities",
    "ModelMessage",
    "ModelProviderInfo",
    "StreamChunk",
    "ContextBudget",
    "ContextBudgeter",
    "DownloadResult",
    "HuggingFaceDownloadError",
    "HuggingFaceDownloader",
    "ModelConfigurationError",
    "ModelDownloadError",
    "ModelInferenceError",
    "ModelNotFoundError",
    "ModelProviderError",
    "ModelRoutingError",
    "HardwareProfile",
    "detect_hardware",
    "ModelManager",
    "ModelRoute",
    "ModelRouter",
]
