"""Unit tests for FORGEX git module."""

from __future__ import annotations

import pytest

from forgex.git.manager import GitManager, GitOperationResult, GitSafetyChecker
from pathlib import Path


class TestGitSafetyChecker:
    def test_is_safe_branch(self):
        s = GitSafetyChecker(Path("."))
        assert s.is_safe_branch("feature-x") is True
        assert s.is_safe_branch("main") is False
        assert s.is_safe_branch("master") is False

    def test_is_safe_commit_message(self):
        s = GitSafetyChecker(Path("."))
        assert s.is_safe_commit_message("Add feature") is True
        assert s.is_safe_commit_message("") is False


class TestGitOperationResult:
    def test_result(self):
        r = GitOperationResult(True, "init", "ok")
        assert r.success is True


class TestGitManager:
    def test_is_git_repo_false(self, tmp_path):
        g = GitManager(tmp_path)
        assert g.is_git_repo() is False
