"""Unit tests for FORGEX verification."""

from __future__ import annotations

import pytest

from forgex.verification.code_verifier import CodeVerifier, VerificationResult
from forgex.verification.change_validator import ChangeValidator
from forgex.verification.result_verifier import ResultVerifier


class TestVerificationResult:
    def test_add_check(self):
        r = VerificationResult(passed=True)
        r.add_check("syntax", True, "ok")
        assert r.passed is True

    def test_add_error(self):
        r = VerificationResult(passed=True)
        r.add_error("fail")
        assert r.passed is False


class TestCodeVerifier:
    def test_verify_python_valid(self, tmp_path):
        f = tmp_path / "valid.py"
        f.write_text("x = 1\n")
        v = CodeVerifier(tmp_path)
        r = v.verify_python_file(f)
        assert r.passed is True

    def test_verify_python_invalid(self, tmp_path):
        f = tmp_path / "bad.py"
        f.write_text("x = \n")
        v = CodeVerifier(tmp_path)
        r = v.verify_python_file(f)
        assert r.passed is False


class TestChangeValidator:
    def test_validate_change(self):
        v = ChangeValidator(".")
        r = v.validate_change("foo.py", "old", "new")
        assert r.valid is True


class TestResultVerifier:
    def test_verify_terminal_success(self):
        v = ResultVerifier()
        r = v.verify_terminal_result(0, "ok", "")
        assert r.verified is True

    def test_verify_terminal_failure(self):
        v = ResultVerifier()
        r = v.verify_terminal_result(1, "", "error")
        assert r.verified is False

    def test_verify_test_result(self):
        v = ResultVerifier()
        r = v.verify_test_result(10, 10, 0, 0)
        assert r.verified is True

    def test_verify_test_result_fail(self):
        v = ResultVerifier()
        r = v.verify_test_result(10, 8, 2, 0)
        assert r.verified is False
