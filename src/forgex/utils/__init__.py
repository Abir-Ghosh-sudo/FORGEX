"""Shared utility functions and helpers for FORGEX."""

from forgex.utils.logging import (
    ForgexLogger,
    configure_logging,
    get_logger,
    shutdown_logging,
)
from forgex.utils.paths import (
    PathValidationError,
    ensure_parent_directory,
    find_files,
    get_platform_name,
    is_within_directory,
    normalize_path,
    resolve_workspace_path,
    safe_relative_path,
    validate_directory,
    validate_file,
)
from forgex.utils.retry import (
    RetryExhaustedError,
    async_retry,
    calculate_backoff,
    retry,
    run_with_timeout,
)
from forgex.utils.serialization import (
    SerializationError,
    canonical_json,
    from_json,
    generate_id,
    generate_short_id,
    sha256_file,
    sha256_text,
    to_json,
    to_primitive,
    utc_now_iso,
)
from forgex.utils.system import (
    HardwareInfo,
    SystemInfo,
    detect_gpu,
    get_hardware_info,
    get_memory_info,
    get_system_info,
    get_system_report,
)

__all__ = [
    # Logging
    "ForgexLogger",
    "configure_logging",
    "get_logger",
    "shutdown_logging",

    # Paths
    "PathValidationError",
    "normalize_path",
    "validate_directory",
    "validate_file",
    "is_within_directory",
    "resolve_workspace_path",
    "ensure_parent_directory",
    "safe_relative_path",
    "find_files",
    "get_platform_name",

    # Retry
    "RetryExhaustedError",
    "calculate_backoff",
    "retry",
    "async_retry",
    "run_with_timeout",

    # Serialization
    "SerializationError",
    "to_json",
    "from_json",
    "canonical_json",
    "generate_id",
    "generate_short_id",
    "sha256_text",
    "sha256_file",
    "utc_now_iso",
    "to_primitive",

    # System
    "SystemInfo",
    "HardwareInfo",
    "get_memory_info",
    "detect_gpu",
    "get_system_info",
    "get_hardware_info",
    "get_system_report",
]