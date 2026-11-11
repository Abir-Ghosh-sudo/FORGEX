"""Serialization and data conversion utilities for FORGEX."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class SerializationError(ValueError):
    """Raised when data cannot be serialized or deserialized."""


def _json_default(value: Any) -> Any:
    """Convert supported Python objects into JSON-compatible values."""

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")

    if isinstance(value, uuid.UUID):
        return str(value)

    if isinstance(value, set):
        return sorted(value, key=str)

    if isinstance(value, bytes):
        return value.hex()

    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable.")


def to_json(
    data: Any,
    *,
    indent: int | None = None,
    sort_keys: bool = False,
) -> str:
    """Serialize Python data into JSON."""

    try:
        return json.dumps(
            data,
            default=_json_default,
            indent=indent,
            sort_keys=sort_keys,
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise SerializationError(f"JSON serialization failed: {exc}") from exc


def from_json(
    content: str | bytes,
    *,
    expected_type: type[T] | None = None,
) -> Any | T:
    """Deserialize JSON into Python data.

    If expected_type is a Pydantic model, validate the decoded data
    against that model.
    """

    try:
        data = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
        raise SerializationError(f"JSON deserialization failed: {exc}") from exc

    if expected_type is None:
        return data

    if isinstance(expected_type, type) and issubclass(
        expected_type,
        BaseModel,
    ):
        try:
            return expected_type.model_validate(data)
        except Exception as exc:
            raise SerializationError(f"JSON model validation failed: {exc}") from exc

    if not isinstance(data, expected_type):
        raise SerializationError(
            f"Expected {expected_type.__name__}, received {type(data).__name__}."
        )

    return data


def canonical_json(data: Any) -> str:
    """Return deterministic JSON suitable for hashing."""

    return to_json(
        data,
        sort_keys=True,
        indent=None,
    )


def generate_id() -> str:
    """Generate a unique UUID4 identifier."""

    return str(uuid.uuid4())


def generate_short_id(length: int = 12) -> str:
    """Generate a short hexadecimal identifier."""

    if not 4 <= length <= 32:
        raise ValueError("Identifier length must be between 4 and 32.")

    return uuid.uuid4().hex[:length]


def sha256_text(value: str) -> str:
    """Calculate the SHA-256 digest of UTF-8 text."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(
    path: str | Path,
    *,
    chunk_size: int = 1024 * 1024,
) -> str:
    """Calculate a file's SHA-256 digest without loading it entirely."""

    if chunk_size < 1:
        raise ValueError("chunk_size must be positive.")

    file_path = Path(path).expanduser().resolve()

    if not file_path.is_file():
        raise FileNotFoundError(f"Cannot hash missing file: {file_path}")

    digest = hashlib.sha256()

    try:
        with file_path.open("rb") as file:
            while chunk := file.read(chunk_size):
                digest.update(chunk)
    except OSError as exc:
        raise SerializationError(f"Failed to hash file: {file_path}") from exc

    return digest.hexdigest()


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""

    return datetime.now(UTC).isoformat()


def to_primitive(data: Any) -> Any:
    """Convert nested supported objects into JSON-compatible values."""

    if isinstance(data, BaseModel):
        return data.model_dump(mode="json")

    if isinstance(data, dict):
        return {str(key): to_primitive(value) for key, value in data.items()}

    if isinstance(data, (list, tuple)):
        return [to_primitive(item) for item in data]

    if isinstance(data, set):
        return [to_primitive(item) for item in sorted(data, key=str)]

    if isinstance(data, (str, int, float, bool)) or data is None:
        return data

    return _json_default(data)


__all__ = [
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
]
