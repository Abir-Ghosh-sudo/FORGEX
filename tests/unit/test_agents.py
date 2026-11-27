"""Unit tests for FORGEX agents."""

from __future__ import annotations

import pytest

from forgex.models.base import GenerationResult

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



@pytest.mark.asyncio
async def test_agent_role_prefers_native_async_model_generation():
    class AsyncModel:
        def __init__(self):
            self.async_called = False
            self.sync_called = False

        async def generate_async(self, messages, **kwargs):
            self.async_called = True
            return GenerationResult(
                text='{"summary": "done", "steps": []}',
                model="test-model",
                provider="test",
            )

        def generate(self, messages, **kwargs):
            self.sync_called = True
            raise AssertionError("Synchronous generation should not be used.")

    model = AsyncModel()
    result = await PlannerRole(model=model).run({"task": "test task"})

    assert result.data["summary"] == "done"
    assert model.async_called is True
    assert model.sync_called is False
