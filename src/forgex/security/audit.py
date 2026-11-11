
"""Security audit logging and integrity verification for FORGEX."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from forgex.security.secrets import SecretScanner


class AuditEventType(StrEnum):
    AUTHENTICATION = "authentication"
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_DENIED = "permission_denied"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_REJECTED = "approval_rejected"
    COMMAND_EXECUTED = "command_executed"
    COMMAND_BLOCKED = "command_blocked"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    SANDBOX_VIOLATION = "sandbox_violation"
    SECURITY_CONFIGURATION = "security_configuration"
    SECRET_DETECTED = "secret_detected"
    SESSION_SECURITY = "session_security"
    SYSTEM_EVENT = "system_event"


class AuditOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    BLOCKED = "blocked"
    PENDING = "pending"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """An immutable security audit event."""

    event_type: AuditEventType
    actor: str
    action: str
    outcome: AuditOutcome

    resource: str | None = None
    reason: str | None = None
    session_id: str | None = None
    workspace: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )

    def __post_init__(self) -> None:
        for name in ("actor", "action"):
            value = getattr(self, name)

            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} cannot be empty.")

        if not isinstance(self.event_type, AuditEventType):
            raise TypeError("event_type must be an AuditEventType.")

        if not isinstance(self.outcome, AuditOutcome):
            raise TypeError("outcome must be an AuditOutcome.")

        for name in ("resource", "reason", "session_id", "workspace"):
            value = getattr(self, name)

            if value is not None and not isinstance(value, str):
                raise TypeError(f"{name} must be a string or None.")

        try:
            uuid.UUID(self.event_id)
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("event_id must be a valid UUID.") from exc

        try:
            parsed = datetime.fromisoformat(self.timestamp)
        except (ValueError, TypeError) as exc:
            raise ValueError("timestamp must be an ISO-8601 datetime.") from exc

        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timestamp must include timezone information.")

        if not isinstance(self.metadata, dict):
            raise TypeError("metadata must be a dictionary.")


@dataclass(frozen=True, slots=True)
class AuditRecord:
    """Serialized event with its integrity-chain information."""

    event: dict[str, Any]
    sequence: int
    previous_hash: str
    record_hash: str


@dataclass(frozen=True, slots=True)
class AuditVerificationResult:
    """Result of verifying an audit log."""

    valid: bool
    records_checked: int
    failed_sequence: int | None = None
    reason: str | None = None


class AuditLogger:
    """Thread-safe, hash-chained JSONL security audit logger.

    Each record contains:
    - A serialized audit event.
    - A monotonically increasing sequence number.
    - The previous record's hash.
    - Its own SHA-256 hash.

    The hash chain detects accidental modification, deletion,
    insertion and reordering of records.

    This is tamper-evident, not tamper-proof. An attacker who can
    rewrite the entire log can also recompute its hash chain.

    This implementation coordinates threads within one process.
    It does not provide cross-process write locking or external
    cryptographic anchoring.
    """

    GENESIS_HASH = "0" * 64

    def __init__(
        self,
        log_path: str | Path,
        *,
        scanner: SecretScanner | None = None,
        fsync: bool = True,
        max_record_bytes: int = 1_000_000,
    ) -> None:
        if max_record_bytes < 1024:
            raise ValueError("max_record_bytes must be at least 1024.")

        if not isinstance(fsync, bool):
            raise TypeError("fsync must be a boolean.")

        self.log_path = Path(log_path).expanduser().resolve()
        self.scanner = scanner or SecretScanner()
        self.fsync = fsync
        self.max_record_bytes = max_record_bytes

        self._lock = threading.RLock()
        self._sequence = 0
        self._previous_hash = self.GENESIS_HASH
        self._closed = False

        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        self._initialize_log()

    @staticmethod
    def _canonical_json(value: dict[str, Any]) -> bytes:
        """Serialize JSON deterministically."""

        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")

    @classmethod
    def _calculate_hash(
        cls,
        *,
        event: dict[str, Any],
        sequence: int,
        previous_hash: str,
    ) -> str:
        """Calculate the SHA-256 hash of one audit record."""

        payload = {
            "event": event,
            "sequence": sequence,
            "previous_hash": previous_hash,
        }

        return hashlib.sha256(cls._canonical_json(payload)).hexdigest()

    @staticmethod
    def _valid_hash(value: Any) -> bool:
        """Validate a SHA-256 hexadecimal digest."""

        if not isinstance(value, str) or len(value) != 64:
            return False

        try:
            bytes.fromhex(value)
        except ValueError:
            return False

        return True

    @classmethod
    def _parse_record(cls, data: Any) -> AuditRecord:
        """Validate and convert an untrusted JSON record."""

        if not isinstance(data, dict):
            raise ValueError("Audit record must be a JSON object.")

        required = {
            "event",
            "sequence",
            "previous_hash",
            "record_hash",
        }

        if not required.issubset(data):
            raise ValueError("Audit record is missing required fields.")

        event = data["event"]
        sequence = data["sequence"]
        previous_hash = data["previous_hash"]
        record_hash = data["record_hash"]

        if not isinstance(event, dict):
            raise ValueError("Audit event must be a JSON object.")

        if isinstance(sequence, bool) or not isinstance(sequence, int):
            raise ValueError("Audit sequence must be an integer.")

        if sequence < 1:
            raise ValueError("Audit sequence must be positive.")

        if not cls._valid_hash(previous_hash):
            raise ValueError("Invalid previous hash.")

        if not cls._valid_hash(record_hash):
            raise ValueError("Invalid record hash.")

        return AuditRecord(
            event=event,
            sequence=sequence,
            previous_hash=previous_hash,
            record_hash=record_hash,
        )

    def _initialize_log(self) -> None:
        """Verify existing records and restore chain state."""

        with self._lock:
            if not self.log_path.exists():
                self._create_log_file()
                return

            if self.log_path.is_symlink():
                raise RuntimeError("Audit log must not be a symbolic link.")

            if not self.log_path.is_file():
                raise RuntimeError("Audit log path must be a regular file.")

            result = self.verify()

            if not result.valid:
                raise RuntimeError(
                    "Audit log integrity verification failed: "
                    f"{result.reason}; sequence={result.failed_sequence}"
                )

            if result.records_checked == 0:
                self._sequence = 0
                self._previous_hash = self.GENESIS_HASH
                return

            last_record = self._read_last_record()

            self._sequence = last_record.sequence
            self._previous_hash = last_record.record_hash

    def _create_log_file(self) -> None:
        """Create a private audit log file."""

        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY

        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW

        descriptor = os.open(
            self.log_path,
            flags,
            0o600,
        )

        try:
            if os.name == "posix":
                os.fchmod(descriptor, 0o600)

            if self.fsync:
                os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _read_last_record(self) -> AuditRecord:
        """Read the final non-empty record."""

        last_line: bytes | None = None

        with self.log_path.open("rb") as file:
            for line in file:
                if line.strip():
                    last_line = line

        if last_line is None:
            raise RuntimeError("Audit log unexpectedly contains no records.")

        try:
            data = json.loads(last_line)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RuntimeError("Final audit record is invalid.") from exc

        return self._parse_record(data)

    def _sanitize_event(self, event: AuditEvent) -> dict[str, Any]:
        """Redact secrets from user-controlled event fields."""

        raw = {
            "event_id": event.event_id,
            "timestamp": event.timestamp,
            "event_type": event.event_type.value,
            "actor": event.actor,
            "action": event.action,
            "outcome": event.outcome.value,
            "resource": event.resource,
            "reason": event.reason,
            "session_id": event.session_id,
            "workspace": event.workspace,
            "metadata": event.metadata,
        }

        sanitized = self.scanner.sanitize(raw)

        if not isinstance(sanitized, dict):
            raise ValueError("Sanitized audit event must be a dictionary.")

        encoded = self._canonical_json(sanitized)

        if len(encoded) > self.max_record_bytes:
            raise ValueError("Audit event exceeds the maximum record size.")

        return sanitized

    def _write_all(self, descriptor: int, data: bytes) -> None:
        """Write all bytes, handling partial operating-system writes."""

        view = memoryview(data)

        while view:
            written = os.write(descriptor, view)

            if written <= 0:
                raise OSError("Audit log write made no progress.")

            view = view[written:]

    def record(self, event: AuditEvent) -> AuditRecord:
        """Append one event to the audit log."""

        if not isinstance(event, AuditEvent):
            raise TypeError("record() requires an AuditEvent.")

        with self._lock:
            if self._closed:
                raise RuntimeError("AuditLogger is closed.")

            sanitized = self._sanitize_event(event)

            next_sequence = self._sequence + 1
            previous_hash = self._previous_hash

            record_hash = self._calculate_hash(
                event=sanitized,
                sequence=next_sequence,
                previous_hash=previous_hash,
            )

            record_data = {
                "event": sanitized,
                "sequence": next_sequence,
                "previous_hash": previous_hash,
                "record_hash": record_hash,
            }

            encoded = self._canonical_json(record_data) + b"\n"

            if len(encoded) > self.max_record_bytes:
                raise ValueError("Serialized audit record is too large.")

            flags = os.O_APPEND | os.O_WRONLY

            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW

            descriptor = os.open(self.log_path, flags)

            try:
                if not os.path.isfile(self.log_path):
                    raise OSError("Audit log is not a regular file.")

                self._write_all(descriptor, encoded)

                if self.fsync:
                    os.fsync(descriptor)
            finally:
                os.close(descriptor)

            # Update chain state only after the write succeeds.
            self._sequence = next_sequence
            self._previous_hash = record_hash

            return AuditRecord(
                event=sanitized,
                sequence=next_sequence,
                previous_hash=previous_hash,
                record_hash=record_hash,
            )

    def record_many(
        self,
        events: Iterable[AuditEvent],
    ) -> list[AuditRecord]:
        """Record multiple events sequentially.

        This operation is not atomic: if a later event fails,
        earlier successfully recorded events remain in the log.
        """

        results: list[AuditRecord] = []

        for event in events:
            results.append(self.record(event))

        return results

    def verify(self) -> AuditVerificationResult:
        """Verify sequence continuity and the complete hash chain."""

        with self._lock:
            if not self.log_path.exists():
                return AuditVerificationResult(
                    valid=True,
                    records_checked=0,
                )

            expected_sequence = 1
            expected_previous_hash = self.GENESIS_HASH
            checked = 0

            try:
                with self.log_path.open("rb") as file:
                    for line in file:
                        if not line.strip():
                            continue

                        try:
                            data = json.loads(line)
                            record = self._parse_record(data)

                            if record.sequence != expected_sequence:
                                raise ValueError("Sequence discontinuity.")

                            if not hmac.compare_digest(
                                record.previous_hash,
                                expected_previous_hash,
                            ):
                                raise ValueError("Previous hash mismatch.")

                            calculated_hash = self._calculate_hash(
                                event=record.event,
                                sequence=record.sequence,
                                previous_hash=record.previous_hash,
                            )

                            if not hmac.compare_digest(
                                record.record_hash,
                                calculated_hash,
                            ):
                                raise ValueError("Record hash mismatch.")

                            expected_previous_hash = calculated_hash
                            expected_sequence += 1
                            checked += 1

                        except (
                            KeyError,
                            TypeError,
                            ValueError,
                            json.JSONDecodeError,
                            UnicodeDecodeError,
                        ) as exc:
                            return AuditVerificationResult(
                                valid=False,
                                records_checked=checked,
                                failed_sequence=expected_sequence,
                                reason=str(exc),
                            )

            except OSError as exc:
                return AuditVerificationResult(
                    valid=False,
                    records_checked=checked,
                    failed_sequence=expected_sequence,
                    reason=f"Unable to read audit log: {exc}",
                )

            return AuditVerificationResult(
                valid=True,
                records_checked=checked,
            )

    @property
    def sequence(self) -> int:
        """Return the number of successfully recorded events."""

        with self._lock:
            return self._sequence

    @property
    def is_closed(self) -> bool:
        """Return whether the logger has been closed."""

        with self._lock:
            return self._closed

    def close(self) -> None:
        """Prevent further writes."""

        with self._lock:
            self._closed = True

    def __enter__(self) -> AuditLogger:
        with self._lock:
            if self._closed:
                raise RuntimeError("AuditLogger is closed.")

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        self.close()
