"""Unit tests for FORGEX agents."""

from __future__ import annotations

import pytest

from forgex.agents.roles.planner import PlannerRole
from forgex.agents.roles.coder import CoderRole
from forgex.agents.roles.reviewer import ReviewerRole
from forgex.agents.roles.tester import TesterRole


class TestAgentRoles:
    def test_planner_role(self):
        r = PlannerRole()
        assert r.name == "planner"

    def test_coder_role(self):
        r = CoderRole()
        assert r.name == "coder"

    def test_reviewer_role(self):
        r = ReviewerRole()
        assert r.name == "reviewer"

    def test_tester_role(self):
        r = TesterRole()
        assert r.name == "tester"
