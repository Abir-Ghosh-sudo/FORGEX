"""Agent role implementations for FORGEX."""

from forgex.agents.roles.base import (
    AgentModelProtocol,
    AgentRole,
    AgentRoleResult,
)
from forgex.agents.roles.coder import CoderRole
from forgex.agents.roles.planner import PlannerRole
from forgex.agents.roles.reviewer import ReviewerRole
from forgex.agents.roles.tester import TesterRole

__all__ = [
    "AgentModelProtocol",
    "AgentRole",
    "AgentRoleResult",
    "PlannerRole",
    "CoderRole",
    "ReviewerRole",
    "TesterRole",
]
