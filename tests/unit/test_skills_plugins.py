"""Unit tests for FORGEX skills and plugins."""

from __future__ import annotations

import pytest

from forgex.skills.base import Skill, SkillContext, SkillResult
from forgex.skills.registry import SkillRegistry
from forgex.skills.builtin.coding import CodingSkill
from forgex.plugins.base import Plugin, PluginContext, PluginResult
from forgex.plugins.registry import PluginRegistry


class TestSkill:
    def test_skill_context(self):
        ctx = SkillContext(workspace=".", task="test")
        assert ctx.workspace == "."

    def test_skill_result(self):
        r = SkillResult(success=True, output="done")
        assert r.success is True

    def test_coding_skill(self):
        skill = CodingSkill()
        assert skill.name == "coding"


class TestSkillRegistry:
    def test_register_and_list(self):
        reg = SkillRegistry()
        reg.register(CodingSkill)
        assert "coding" in reg.list_skills()

    def test_create_instance(self):
        reg = SkillRegistry()
        reg.register(CodingSkill)
        skill = reg.create_instance("coding")
        assert isinstance(skill, CodingSkill)


class TestPlugin:
    class MyPlugin(Plugin):
        name = "test-plugin"
        version = "1.0.0"

        async def initialize(self, context):
            return PluginResult(success=True, output="ok")

        async def shutdown(self):
            return PluginResult(success=True, output="ok")

        async def execute(self, action, params):
            return PluginResult(success=True, output=action)

    def test_plugin_registry(self):
        reg = PluginRegistry()
        reg.register(self.MyPlugin)
        assert "test-plugin" in reg.list_plugins()
