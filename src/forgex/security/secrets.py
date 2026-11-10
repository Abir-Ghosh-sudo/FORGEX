
"""Secret detection and redaction engine for FORGEX."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Iterable


class SecretType(StrEnum):
    API_KEY = "api_key"
    ACCESS_TOKEN = "access_token"
    REFRESH_TOKEN = "refresh_token"
    JWT = "jwt"
    PASSWORD = "password"
    PRIVATE_KEY = "private_key"
    AWS_ACCESS_KEY = "aws_access_key"
    AWS_SECRET_KEY = "aws_secret_key"
    GITHUB_TOKEN = "github_token"
    GENERIC_SECRET = "generic_secret"
    DATABASE_URL = "database_url"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class SecretMatch:
    """A detected secret in a text value."""

    secret_type: SecretType
    start: int
    end: int
    confidence: float
    fingerprint: str

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError("Invalid secret match boundaries.")

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Confidence must be between 0 and 1.")


@dataclass(frozen=True, slots=True)
class RedactionResult:
    """Result of scanning and redacting a text value."""

    original_length: int
    redacted_text: str
    matches: tuple[SecretMatch, ...]

    @property
    def contains_secrets(self) -> bool:
        return bool(self.matches)

    @property
    def secret_count(self) -> int:
        return len(self.matches)


@dataclass(frozen=True, slots=True)
class SecretPattern:
    """A custom secret detection pattern."""

    name: str
    pattern: str
    secret_type: SecretType = SecretType.CUSTOM
    confidence: float = 0.9
    flags: int = re.IGNORECASE

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Pattern name cannot be empty.")

        if not self.pattern:
            raise ValueError("Pattern cannot be empty.")

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Confidence must be between 0 and 1.")

        # Validate the regular expression during construction.
        re.compile(self.pattern, self.flags)


class SecretScanner:
    """Detect and redact common credentials and sensitive values.

    The scanner never returns the original secret as part of a match.
    Fingerprints are one-way SHA-256 digests used for correlation.
    """

    REDACTION: str = "[REDACTED]"

    _MAX_INPUT_LENGTH = 5_000_000
    _MAX_PATTERNS = 256

    _DEFAULT_PATTERNS: tuple[SecretPattern, ...] = (
        SecretPattern(
            name="private-key",
            pattern=(
                r"-----BEGIN "
                r"(?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
                r".*?"
                r"-----END "
                r"(?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
            ),
            secret_type=SecretType.PRIVATE_KEY,
            confidence=1.0,
            flags=re.IGNORECASE | re.DOTALL,
        ),
        SecretPattern(
            name="aws-access-key",
            pattern=r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
            secret_type=SecretType.AWS_ACCESS_KEY,
            confidence=0.99,
        ),
        SecretPattern(
            name="github-token",
            pattern=(
                r"\b(?:gh[pousr]_[A-Za-z0-9]{20,255}|"
                r"github_pat_[A-Za-z0-9_]{20,255})\b"
            ),
            secret_type=SecretType.GITHUB_TOKEN,
            confidence=0.99,
        ),
        SecretPattern(
            name="jwt",
            pattern=(
                r"\beyJ[A-Za-z0-9_-]{5,}\."
                r"[A-Za-z0-9_-]{5,}\."
                r"[A-Za-z0-9_-]{5,}\b"
            ),
            secret_type=SecretType.JWT,
            confidence=0.95,
        ),
        SecretPattern(
            name="database-url",
            pattern=(
                r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)"
                r"://[^:\s/@]+:[^@\s]+@[^/\s]+(?:/[^\s]*)?"
            ),
            secret_type=SecretType.DATABASE_URL,
            confidence=0.98,
        ),
        SecretPattern(
            name="bearer-token",
            pattern=r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}",
            secret_type=SecretType.ACCESS_TOKEN,
            confidence=0.98,
        ),
        SecretPattern(
            name="authorization-header",
            pattern=(
                r"(?im)\b(?:authorization|proxy-authorization)"
                r"\s*[:=]\s*(?:Bearer\s+)?[^\s,;]+"
            ),
            secret_type=SecretType.ACCESS_TOKEN,
            confidence=0.99,
        ),
        SecretPattern(
            name="api-key-assignment",
            pattern=(
                r"""(?i)\b(?:api[_-]?key|client[_-]?secret|"""
                r"""access[_-]?token|refresh[_-]?token)\b"""
                r"""\s*[:=]\s*["']?"""
                r"""[A-Za-z0-9_./+=-]{12,}"""
            ),
            secret_type=SecretType.API_KEY,
            confidence=0.96,
        ),
        SecretPattern(
            name="password-assignment",
            pattern=(
                r"""(?i)\b(?:password|passwd|pwd)\b"""
                r"""\s*[:=]\s*["']?"""
                r"""[^\s"',;]{4,}"""
            ),
            secret_type=SecretType.PASSWORD,
            confidence=0.95,
        ),
        SecretPattern(
            name="aws-secret-assignment",
            pattern=(
                r"""(?i)\baws_secret_access_key\b"""
                r"""\s*[:=]\s*["']?"""
                r"""[A-Za-z0-9/+=]{30,}"""
            ),
            secret_type=SecretType.AWS_SECRET_KEY,
            confidence=0.99,
        ),
        SecretPattern(
            name="generic-secret-assignment",
            pattern=(
                r"""(?i)\b(?:secret|credential|private[_-]?key)\b"""
                r"""\s*[:=]\s*["']?"""
                r"""[A-Za-z0-9_./+=-]{12,}"""
            ),
            secret_type=SecretType.GENERIC_SECRET,
            confidence=0.90,
        ),
    )

    def __init__(
        self,
        *,
        patterns: Iterable[SecretPattern] | None = None,
        minimum_confidence: float = 0.70,
        max_input_length: int = _MAX_INPUT_LENGTH,
    ) -> None:
        if not 0.0 <= minimum_confidence <= 1.0:
            raise ValueError("Minimum confidence must be between 0 and 1.")

        if max_input_length < 1:
            raise ValueError("Maximum input length must be positive.")

        self._minimum_confidence = minimum_confidence
        self._max_input_length = max_input_length

        selected = list(self._DEFAULT_PATTERNS)

        if patterns is not None:
            selected.extend(patterns)

        if len(selected) > self._MAX_PATTERNS:
            raise ValueError("Too many secret detection patterns.")

        names = [pattern.name for pattern in selected]

        if len(names) != len(set(names)):
            raise ValueError("Secret pattern names must be unique.")

        self._compiled_patterns = [
            (
                pattern.secret_type,
                pattern.confidence,
                re.compile(pattern.pattern, pattern.flags),
            )
            for pattern in selected
        ]

    @staticmethod
    def _fingerprint(secret: str) -> str:
        """Return a one-way fingerprint without exposing the secret."""

        import hashlib

        return hashlib.sha256(
            secret.encode("utf-8", errors="replace")
        ).hexdigest()

    def scan(self, text: str) -> tuple[SecretMatch, ...]:
        """Find sensitive values in text."""

        if not isinstance(text, str):
            raise TypeError("SecretScanner.scan expects a string.")

        if len(text) > self._max_input_length:
            raise ValueError("Input exceeds the configured scanning limit.")

        candidates: list[SecretMatch] = []

        for secret_type, confidence, pattern in self._compiled_patterns:
            if confidence < self._minimum_confidence:
                continue

            for match in pattern.finditer(text):
                secret = match.group(0)

                if not secret:
                    continue

                candidates.append(
                    SecretMatch(
                        secret_type=secret_type,
                        start=match.start(),
                        end=match.end(),
                        confidence=confidence,
                        fingerprint=self._fingerprint(secret),
                    )
                )

        return self._resolve_overlaps(candidates)

    @staticmethod
    def _resolve_overlaps(
        candidates: list[SecretMatch],
    ) -> tuple[SecretMatch, ...]:
        """Prefer high-confidence and longer matches without overlap."""

        ordered = sorted(
            candidates,
            key=lambda match: (
                -match.confidence,
                -(match.end - match.start),
                match.start,
            ),
        )

        accepted: list[SecretMatch] = []

        for candidate in ordered:
            overlaps = any(
                candidate.start < existing.end
                and candidate.end > existing.start
                for existing in accepted
            )

            if not overlaps:
                accepted.append(candidate)

        accepted.sort(key=lambda match: match.start)

        return tuple(accepted)

    def redact(self, text: str) -> RedactionResult:
        """Replace detected secrets with a redaction marker."""

        matches = self.scan(text)

        if not matches:
            return RedactionResult(
                original_length=len(text),
                redacted_text=text,
                matches=(),
            )

        parts: list[str] = []
        cursor = 0

        for match in matches:
            parts.append(text[cursor:match.start])
            parts.append(self.REDACTION)
            cursor = match.end

        parts.append(text[cursor:])

        return RedactionResult(
            original_length=len(text),
            redacted_text="".join(parts),
            matches=matches,
        )

    def contains_secrets(self, text: str) -> bool:
        """Return whether text contains a detected secret."""

        return bool(self.scan(text))

    def sanitize(
        self,
        value: Any,
        *,
        max_depth: int = 20,
    ) -> Any:
        """Recursively sanitize strings in dictionaries and collections.

        Dictionary keys are also scanned and redacted.
        Unsupported object types are converted to a safe placeholder
        rather than calling arbitrary object representations.
        """

        if max_depth < 0:
            raise ValueError("Maximum recursion depth cannot be negative.")

        return self._sanitize_value(value, depth=0, max_depth=max_depth)

    def _sanitize_value(
        self,
        value: Any,
        *,
        depth: int,
        max_depth: int,
    ) -> Any:
        if depth > max_depth:
            return "[MAX_DEPTH_REACHED]"

        if isinstance(value, str):
            return self.redact(value).redacted_text

        if isinstance(value, dict):
            result: dict[str, Any] = {}

            for key, item in value.items():
                safe_key = (
                    self.redact(key).redacted_text
                    if isinstance(key, str)
                    else "[NON_STRING_KEY]"
                )

                result[safe_key] = self._sanitize_value(
                    item,
                    depth=depth + 1,
                    max_depth=max_depth,
                )

            return result

        if isinstance(value, list):
            return [
                self._sanitize_value(
                    item,
                    depth=depth + 1,
                    max_depth=max_depth,
                )
                for item in value
            ]

        if isinstance(value, tuple):
            return tuple(
                self._sanitize_value(
                    item,
                    depth=depth + 1,
                    max_depth=max_depth,
                )
                for item in value
            )

        if isinstance(value, set):
            return {
                self._sanitize_value(
                    item,
                    depth=depth + 1,
                    max_depth=max_depth,
                )
                for item in value
            }

        if value is None or isinstance(value, (bool, int, float)):
            return value

        return f"[UNSUPPORTED_TYPE:{type(value).__name__}]"

    def add_pattern(self, pattern: SecretPattern) -> None:
        """Register a custom detection pattern."""

        if any(
            existing_name == pattern.name
            for _, _, compiled in self._compiled_patterns
            for existing_name in ()
        ):
            raise ValueError(f"Duplicate pattern: {pattern.name}")

        if len(self._compiled_patterns) >= self._MAX_PATTERNS:
            raise ValueError("Maximum secret pattern count reached.")

        compiled = re.compile(pattern.pattern, pattern.flags)

        self._compiled_patterns.append(
            (
                pattern.secret_type,
                pattern.confidence,
                compiled,
            )
        )


def redact_secrets(text: str) -> str:
    """Convenience function for redacting common secrets."""

    return SecretScanner().redact(text).redacted_text
