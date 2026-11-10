
"""Unit tests for FORGEX security audit logging."""

from __future__ import annotations

import json
import os

from pathlib import Path

import pytest

from forgex.security.audit import (
    AuditEvent,
    AuditEventType,
    AuditLogger,
    AuditOutcome,
    AuditVerificationResult,
)


def make_event(
    *,
    actor: str = "test-user",
    action: str = "test-action",
    outcome: AuditOutcome = AuditOutcome.SUCCESS,
    metadata: dict | None = None,
) -> AuditEvent:
    """Create a reusable audit event."""

    return AuditEvent(
        event_type=AuditEventType.SYSTEM_EVENT,
        actor=actor,
        action=action,
        outcome=outcome,
        metadata=metadata or {},
    )


@pytest.fixture
def logger(tmp_path: Path) -> AuditLogger:
    """Create an audit logger for a temporary file."""

    return AuditLogger(
        tmp_path / "audit.jsonl",
        fsync=False,
    )


class TestAuditEvent:
    def test_create_valid_event(self) -> None:
        event = make_event()

        assert event.actor == "test-user"
        assert event.action == "test-action"
        assert event.outcome == AuditOutcome.SUCCESS
        assert event.event_id

    def test_reject_empty_actor(self) -> None:
        with pytest.raises(ValueError, match="actor"):
            make_event(actor=" ")

    def test_reject_empty_action(self) -> None:
        with pytest.raises(ValueError, match="action"):
            make_event(action="")

    def test_reject_invalid_event_type(self) -> None:
        with pytest.raises(TypeError, match="event_type"):
            AuditEvent(
                event_type="invalid",  # type: ignore[arg-type]
                actor="user",
                action="test",
                outcome=AuditOutcome.SUCCESS,
            )

    def test_reject_invalid_outcome(self) -> None:
        with pytest.raises(TypeError, match="outcome"):
            AuditEvent(
                event_type=AuditEventType.SYSTEM_EVENT,
                actor="user",
                action="test",
                outcome="invalid",  # type: ignore[arg-type]
            )

    def test_reject_invalid_uuid(self) -> None:
        with pytest.raises(ValueError, match="UUID"):
            AuditEvent(
                event_type=AuditEventType.SYSTEM_EVENT,
                actor="user",
                action="test",
                outcome=AuditOutcome.SUCCESS,
                event_id="not-a-uuid",
            )

    def test_reject_timestamp_without_timezone(self) -> None:
        with pytest.raises(ValueError, match="timezone"):
            AuditEvent(
                event_type=AuditEventType.SYSTEM_EVENT,
                actor="user",
                action="test",
                outcome=AuditOutcome.SUCCESS,
                timestamp="2026-01-01T12:00:00",
            )

    def test_reject_non_dictionary_metadata(self) -> None:
        with pytest.raises(TypeError, match="metadata"):
            AuditEvent(
                event_type=AuditEventType.SYSTEM_EVENT,
                actor="user",
                action="test",
                outcome=AuditOutcome.SUCCESS,
                metadata=[],  # type: ignore[arg-type]
            )


class TestAuditLogger:
    def test_creates_log_file(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"

        AuditLogger(path, fsync=False)

        assert path.exists()
        assert path.is_file()

    def test_initial_sequence_is_zero(self, logger: AuditLogger) -> None:
        assert logger.sequence == 0

    def test_record_single_event(self, logger: AuditLogger) -> None:
        record = logger.record(make_event())

        assert record.sequence == 1
        assert len(record.record_hash) == 64
        assert record.previous_hash == AuditLogger.GENESIS_HASH
        assert logger.sequence == 1

    def test_record_multiple_events(self, logger: AuditLogger) -> None:
        first = logger.record(make_event(action="first"))
        second = logger.record(make_event(action="second"))
        third = logger.record(make_event(action="third"))

        assert first.sequence == 1
        assert second.sequence == 2
        assert third.sequence == 3

        assert second.previous_hash == first.record_hash
        assert third.previous_hash == second.record_hash

        assert logger.sequence == 3

    def test_record_many(self, logger: AuditLogger) -> None:
        records = logger.record_many(
            make_event(action=f"action-{index}")
            for index in range(5)
        )

        assert len(records) == 5
        assert [record.sequence for record in records] == [
            1, 2, 3, 4, 5
        ]
        assert logger.sequence == 5

    def test_reject_non_audit_event(self, logger: AuditLogger) -> None:
        with pytest.raises(TypeError, match="AuditEvent"):
            logger.record("invalid")  # type: ignore[arg-type]

    def test_verify_empty_log(self, logger: AuditLogger) -> None:
        result = logger.verify()

        assert isinstance(result, AuditVerificationResult)
        assert result.valid is True
        assert result.records_checked == 0

    def test_verify_valid_log(self, logger: AuditLogger) -> None:
        logger.record(make_event())
        logger.record(make_event(action="second"))

        result = logger.verify()

        assert result.valid is True
        assert result.records_checked == 2
        assert result.failed_sequence is None

    def test_restore_sequence_after_reopening(
        self,
        tmp_path: Path,
    ) -> None:
        path = tmp_path / "audit.jsonl"

        first_logger = AuditLogger(path, fsync=False)
        first_logger.record(make_event())
        first_logger.record(make_event(action="second"))
        first_logger.close()

        second_logger = AuditLogger(path, fsync=False)

        assert second_logger.sequence == 2

        record = second_logger.record(make_event(action="third"))

        assert record.sequence == 3
        assert second_logger.verify().valid is True

    def test_record_contains_sanitized_event(
        self,
        logger: AuditLogger,
        tmp_path: Path,
    ) -> None:
        secret = "super-secret-password-123"

        logger.record(
            make_event(
                metadata={"password": secret},
            )
        )

        content = (
            tmp_path / "audit.jsonl"
        ).read_text(encoding="utf-8")

        assert secret not in content
        assert "[REDACTED]" in content

    def test_sanitize_secret_in_nested_metadata(
        self,
        logger: AuditLogger,
        tmp_path: Path,
    ) -> None:
        secret = "my-private-api-key-123456"

        logger.record(
            make_event(
                metadata={
                    "credentials": {
                        "api_key": secret,
                        "username": "developer",
                    }
                }
            )
        )

        content = (
            tmp_path / "audit.jsonl"
        ).read_text(encoding="utf-8")

        assert secret not in content
        assert "developer" in content
        assert "[REDACTED]" in content

    def test_reject_oversized_record(self, tmp_path: Path) -> None:
        logger = AuditLogger(
            tmp_path / "large.jsonl",
            fsync=False,
            max_record_bytes=1024,
        )

        event = make_event(
            metadata={"description": "A" * 5000},
        )

        with pytest.raises(ValueError, match="maximum record size"):
            logger.record(event)

        assert logger.sequence == 0

    def test_reject_invalid_max_record_size(
        self,
        tmp_path: Path,
    ) -> None:
        with pytest.raises(ValueError, match="at least 1024"):
            AuditLogger(
                tmp_path / "invalid.jsonl",
                max_record_bytes=100,
            )

    def test_record_after_close_fails(
        self,
        logger: AuditLogger,
    ) -> None:
        logger.close()

        assert logger.is_closed is True

        with pytest.raises(RuntimeError, match="closed"):
            logger.record(make_event())

    def test_context_manager_closes_logger(
        self,
        tmp_path: Path,
    ) -> None:
        path = tmp_path / "context.jsonl"

        with AuditLogger(path, fsync=False) as audit:
            audit.record(make_event())
            assert audit.is_closed is False

        assert audit.is_closed is True

        with pytest.raises(RuntimeError, match="closed"):
            audit.record(make_event())

    def test_reject_reentering_closed_logger(
        self,
        tmp_path: Path,
    ) -> None:
        audit = AuditLogger(
            tmp_path / "closed.jsonl",
            fsync=False,
        )
        audit.close()

        with pytest.raises(RuntimeError, match="closed"):
            audit.__enter__()

    def test_sequence_does_not_advance_on_failed_record(
        self,
        logger: AuditLogger,
    ) -> None:
        with pytest.raises(TypeError):
            logger.record("invalid")  # type: ignore[arg-type]

        assert logger.sequence == 0

    def test_verify_accepts_blank_lines(
        self,
        logger: AuditLogger,
        tmp_path: Path,
    ) -> None:
        logger.record(make_event())

        path = tmp_path / "audit.jsonl"

        with path.open("ab") as file:
            file.write(b"\n")

        result = logger.verify()

        assert result.valid is True
        assert result.records_checked == 1

    def test_detect_modified_event(
        self,
        logger: AuditLogger,
        tmp_path: Path,
    ) -> None:
        logger.record(make_event())

        path = tmp_path / "audit.jsonl"
        data = json.loads(path.read_text(encoding="utf-8"))

        data["event"]["action"] = "modified-action"

        path.write_text(
            json.dumps(data) + "\n",
            encoding="utf-8",
        )

        result = logger.verify()

        assert result.valid is False
        assert result.records_checked == 0
        assert result.reason == "Record hash mismatch."

    def test_detect_modified_record_hash(
        self,
        logger: AuditLogger,
        tmp_path: Path,
    ) -> None:
        logger.record(make_event())

        path = tmp_path / "audit.jsonl"
        data = json.loads(path.read_text(encoding="utf-8"))

        data["record_hash"] = "f" * 64

        path.write_text(
            json.dumps(data) + "\n",
            encoding="utf-8",
        )

        result = logger.verify()

        assert result.valid is False
        assert result.reason == "Record hash mismatch."

    def test_detect_sequence_discontinuity(
        self,
        logger: AuditLogger,
        tmp_path: Path,
    ) -> None:
        logger.record(make_event())

        path = tmp_path / "audit.jsonl"
        data = json.loads(path.read_text(encoding="utf-8"))

        data["sequence"] = 5

        path.write_text(
            json.dumps(data) + "\n",
            encoding="utf-8",
        )

        result = logger.verify()

        assert result.valid is False
        assert result.reason == "Sequence discontinuity."

    def test_detect_previous_hash_mismatch(
        self,
        logger: AuditLogger,
        tmp_path: Path,
    ) -> None:
        logger.record(make_event())

        path = tmp_path / "audit.jsonl"
        data = json.loads(path.read_text(encoding="utf-8"))

        data["previous_hash"] = "a" * 64

        path.write_text(
            json.dumps(data) + "\n",
            encoding="utf-8",
        )

        result = logger.verify()

        assert result.valid is False
        assert result.reason == "Previous hash mismatch."

    def test_detect_malformed_json(
        self,
        logger: AuditLogger,
        tmp_path: Path,
    ) -> None:
        path = tmp_path / "audit.jsonl"
        path.write_text(
            "{invalid-json}\n",
            encoding="utf-8",
        )

        result = logger.verify()

        assert result.valid is False
        assert result.records_checked == 0
        assert result.failed_sequence == 1

    def test_detect_missing_record_fields(
        self,
        logger: AuditLogger,
        tmp_path: Path,
    ) -> None:
        path = tmp_path / "audit.jsonl"
        path.write_text(
            json.dumps({"sequence": 1}) + "\n",
            encoding="utf-8",
        )

        result = logger.verify()

        assert result.valid is False
        assert "missing required fields" in result.reason

    def test_reject_corrupted_log_during_initialization(
        self,
        tmp_path: Path,
    ) -> None:
        path = tmp_path / "corrupted.jsonl"

        path.write_text(
            "{broken}\n",
            encoding="utf-8",
        )

        with pytest.raises(RuntimeError, match="integrity"):
            AuditLogger(path, fsync=False)

    def test_verify_missing_log_file(
        self,
        tmp_path: Path,
    ) -> None:
        audit = AuditLogger(
            tmp_path / "missing.jsonl",
            fsync=False,
        )

        audit.log_path.unlink()

        result = audit.verify()

        assert result.valid is True
        assert result.records_checked == 0

    @pytest.mark.skipif(
        os.name != "posix",
        reason="POSIX file permission test",
    )
    def test_log_file_has_private_permissions(
        self,
        tmp_path: Path,
    ) -> None:
        path = tmp_path / "private.jsonl"

        AuditLogger(path, fsync=False)

        mode = path.stat().st_mode & 0o777

        assert mode == 0o600
