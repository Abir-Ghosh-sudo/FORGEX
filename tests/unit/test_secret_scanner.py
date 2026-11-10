
"""Unit tests for FORGEX secret detection and redaction."""

import pytest

from forgex.security.secrets import (
    RedactionResult,
    SecretPattern,
    SecretScanner,
    SecretType,
    redact_secrets,
)


@pytest.fixture
def scanner() -> SecretScanner:
    return SecretScanner()


class TestSecretScanner:
    """Tests for secret detection."""

    def test_detect_github_token(self, scanner):
        text = "GITHUB_TOKEN=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"
        matches = scanner.scan(text)

        assert matches
        assert any(
            match.secret_type == SecretType.GITHUB_TOKEN
            for match in matches
        )

    def test_detect_aws_access_key(self, scanner):
        text = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"
        matches = scanner.scan(text)

        assert any(
            match.secret_type == SecretType.AWS_ACCESS_KEY
            for match in matches
        )

    def test_detect_jwt(self, scanner):
        text = (
            "token=eyJhbGciOiJIUzI1NiJ9."
            "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
            "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        )

        matches = scanner.scan(text)

        assert any(
            match.secret_type == SecretType.JWT
            for match in matches
        )

    def test_detect_password_assignment(self, scanner):
        text = "password=supersecret123"
        matches = scanner.scan(text)

        assert any(
            match.secret_type == SecretType.PASSWORD
            for match in matches
        )

    def test_detect_api_key_assignment(self, scanner):
        text = "api_key=sk_test_1234567890abcdef"
        matches = scanner.scan(text)

        assert any(
            match.secret_type == SecretType.API_KEY
            for match in matches
        )

    def test_detect_bearer_token(self, scanner):
        text = "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456"
        matches = scanner.scan(text)

        assert any(
            match.secret_type == SecretType.ACCESS_TOKEN
            for match in matches
        )

    def test_detect_private_key(self, scanner):
        text = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEpAIBAAKCAQEAExamplePrivateKeyMaterial\n"
            "-----END RSA PRIVATE KEY-----"
        )

        matches = scanner.scan(text)

        assert any(
            match.secret_type == SecretType.PRIVATE_KEY
            for match in matches
        )

    def test_detect_database_url(self, scanner):
        text = "DATABASE_URL=postgresql://admin:secret123@localhost:5432/app"

        matches = scanner.scan(text)

        assert any(
            match.secret_type == SecretType.DATABASE_URL
            for match in matches
        )

    def test_detect_generic_secret(self, scanner):
        text = "secret=abcdefghijklmnopqrstuvwxyz123456"

        matches = scanner.scan(text)

        assert any(
            match.secret_type == SecretType.GENERIC_SECRET
            for match in matches
        )

    def test_detect_aws_secret_assignment(self, scanner):
        text = (
            "aws_secret_access_key="
            "abcdefghijklmnopqrstuvwxyz1234567890ABCD"
        )

        matches = scanner.scan(text)

        assert any(
            match.secret_type == SecretType.AWS_SECRET_KEY
            for match in matches
        )

    def test_clean_text_has_no_matches(self, scanner):
        text = "Hello, FORGEX! This is a normal message."

        assert scanner.scan(text) == ()
        assert not scanner.contains_secrets(text)

    def test_contains_secrets_returns_true(self, scanner):
        text = "password=mysecretpassword123"

        assert scanner.contains_secrets(text)

    def test_scan_returns_tuple(self, scanner):
        result = scanner.scan("api_key=sk_test_1234567890abcdef")

        assert isinstance(result, tuple)

    def test_match_has_valid_boundaries(self, scanner):
        text = "password=supersecret123"
        matches = scanner.scan(text)

        assert matches

        for match in matches:
            assert 0 <= match.start < match.end <= len(text)

    def test_match_has_valid_confidence(self, scanner):
        matches = scanner.scan("password=supersecret123")

        for match in matches:
            assert 0.0 <= match.confidence <= 1.0

    def test_match_fingerprint_does_not_contain_secret(self, scanner):
        secret = "supersecretpassword123"
        matches = scanner.scan(f"password={secret}")

        assert matches

        for match in matches:
            assert secret not in match.fingerprint
            assert len(match.fingerprint) == 64


class TestSecretRedaction:
    """Tests for secret redaction."""

    def test_redact_password(self, scanner):
        text = "password=supersecret123"

        result = scanner.redact(text)

        assert isinstance(result, RedactionResult)
        assert result.contains_secrets
        assert "[REDACTED]" in result.redacted_text
        assert "supersecret123" not in result.redacted_text

    def test_redact_github_token(self, scanner):
        token = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"
        result = scanner.redact(f"token={token}")

        assert token not in result.redacted_text
        assert "[REDACTED]" in result.redacted_text

    def test_redact_multiple_secrets(self, scanner):
        text = (
            "password=supersecret123\n"
            "api_key=sk_test_1234567890abcdef"
        )

        result = scanner.redact(text)

        assert result.secret_count >= 2
        assert "supersecret123" not in result.redacted_text
        assert "sk_test_1234567890abcdef" not in result.redacted_text

    def test_redact_preserves_safe_text(self, scanner):
        text = "Hello password=supersecret123 welcome"

        result = scanner.redact(text)

        assert result.redacted_text.startswith("Hello ")
        assert result.redacted_text.endswith(" welcome")

    def test_redact_clean_text_unchanged(self, scanner):
        text = "This text contains no secrets."

        result = scanner.redact(text)

        assert result.redacted_text == text
        assert result.secret_count == 0

    def test_redaction_result_original_length(self, scanner):
        text = "password=supersecret123"

        result = scanner.redact(text)

        assert result.original_length == len(text)

    def test_redact_secrets_convenience_function(self):
        text = "password=supersecret123"

        result = redact_secrets(text)

        assert "supersecret123" not in result
        assert "[REDACTED]" in result


class TestSecretSanitization:
    """Tests for recursive object sanitization."""

    def test_sanitize_dictionary(self, scanner):
        data = {
            "username": "abir",
            "password": "supersecret123",
        }

        result = scanner.sanitize(data)

        assert result["username"] == "abir"
        assert "supersecret123" not in result["password"]

    def test_sanitize_nested_dictionary(self, scanner):
        data = {
            "user": {
                "name": "abir",
                "credentials": {
                    "api_key": "sk_test_1234567890abcdef",
                },
            },
        }

        result = scanner.sanitize(data)

        assert result["user"]["name"] == "abir"
        assert "sk_test_1234567890abcdef" not in (
            result["user"]["credentials"]["api_key"]
        )

    def test_sanitize_list(self, scanner):
        data = [
            "normal text",
            "password=supersecret123",
        ]

        result = scanner.sanitize(data)

        assert result[0] == "normal text"
        assert "supersecret123" not in result[1]

    def test_sanitize_tuple(self, scanner):
        data = ("normal text", "password=supersecret123")

        result = scanner.sanitize(data)

        assert isinstance(result, tuple)
        assert "supersecret123" not in result[1]

    def test_sanitize_set(self, scanner):
        data = {"normal text", "password=supersecret123"}

        result = scanner.sanitize(data)

        assert isinstance(result, set)
        assert all("supersecret123" not in item for item in result)

    def test_sanitize_preserves_primitive_values(self, scanner):
        data = {
            "enabled": True,
            "count": 10,
            "ratio": 1.5,
            "value": None,
        }

        result = scanner.sanitize(data)

        assert result == data

    def test_sanitize_redacts_dictionary_keys(self, scanner):
        data = {
            "password=supersecret123": "value",
        }

        result = scanner.sanitize(data)

        assert "password=supersecret123" not in result
        assert "[REDACTED]" in result

    def test_sanitize_maximum_depth(self, scanner):
        data = {"a": {"b": {"c": "value"}}}

        result = scanner.sanitize(data, max_depth=1)

        assert result["a"]["b"] == "[MAX_DEPTH_REACHED]"

    def test_sanitize_rejects_negative_depth(self, scanner):
        with pytest.raises(ValueError):
            scanner.sanitize({}, max_depth=-1)

    def test_sanitize_unsupported_object(self, scanner):
        class CustomObject:
            pass

        result = scanner.sanitize(CustomObject())

        assert result == "[UNSUPPORTED_TYPE:CustomObject]"


class TestCustomSecretPatterns:
    """Tests for user-defined detection patterns."""

    def test_custom_pattern_detection(self):
        pattern = SecretPattern(
            name="internal-token",
            pattern=r"\bFORGEX_[A-Z0-9]{16}\b",
            secret_type=SecretType.CUSTOM,
            confidence=0.99,
        )

        scanner = SecretScanner(patterns=[pattern])

        matches = scanner.scan("token=FORGEX_ABCDEFGHIJKLMNOP")

        assert any(
            match.secret_type == SecretType.CUSTOM
            for match in matches
        )

    def test_custom_pattern_redaction(self):
        pattern = SecretPattern(
            name="custom-password",
            pattern=r"MYSECRET_[A-Z0-9]{12}",
        )

        scanner = SecretScanner(patterns=[pattern])

        result = scanner.redact("value=MYSECRET_ABCDEFGHIJKL")

        assert "MYSECRET_ABCDEFGHIJKL" not in result.redacted_text

    def test_custom_pattern_confidence_filter(self):
        pattern = SecretPattern(
            name="low-confidence",
            pattern=r"LOWCONF_[A-Z0-9]{12}",
            confidence=0.50,
        )

        scanner = SecretScanner(
            patterns=[pattern],
            minimum_confidence=0.80,
        )

        assert scanner.scan("LOWCONF_ABCDEFGHIJKL") == ()

    def test_add_custom_pattern(self):
        scanner = SecretScanner()

        scanner.add_pattern(
            SecretPattern(
                name="deployment-token",
                pattern=r"DEPLOY_[A-Z0-9]{16}",
            )
        )

        matches = scanner.scan("DEPLOY_ABCDEFGHIJKLMNOP")

        assert matches
        assert any(
            match.secret_type == SecretType.CUSTOM
            for match in matches
        )

    def test_invalid_pattern_rejected(self):
        with pytest.raises(Exception):
            SecretPattern(
                name="invalid",
                pattern="[",
            )

    def test_invalid_confidence_rejected(self):
        with pytest.raises(ValueError):
            SecretPattern(
                name="invalid-confidence",
                pattern=r"SECRET_[A-Z]+",
                confidence=1.5,
            )

    def test_invalid_scanner_confidence_rejected(self):
        with pytest.raises(ValueError):
            SecretScanner(minimum_confidence=2.0)

    def test_invalid_max_input_length_rejected(self):
        with pytest.raises(ValueError):
            SecretScanner(max_input_length=0)


class TestSecretScannerValidation:
    """Tests for input validation and safety limits."""

    def test_scan_rejects_non_string(self, scanner):
        with pytest.raises(TypeError):
            scanner.scan(123)

    def test_scan_rejects_oversized_input(self):
        scanner = SecretScanner(max_input_length=10)

        with pytest.raises(ValueError):
            scanner.scan("A" * 11)

    def test_scan_accepts_input_at_limit(self):
        scanner = SecretScanner(max_input_length=10)

        assert scanner.scan("A" * 10) == ()

    def test_secret_match_rejects_invalid_boundaries(self):
        from forgex.security.secrets import SecretMatch

        with pytest.raises(ValueError):
            SecretMatch(
                secret_type=SecretType.API_KEY,
                start=5,
                end=3,
                confidence=0.9,
                fingerprint="a" * 64,
            )

    def test_secret_match_rejects_invalid_confidence(self):
        from forgex.security.secrets import SecretMatch

        with pytest.raises(ValueError):
            SecretMatch(
                secret_type=SecretType.API_KEY,
                start=0,
                end=5,
                confidence=2.0,
                fingerprint="a" * 64,
            )
