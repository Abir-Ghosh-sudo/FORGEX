"""Default agent workflow wiring for FORGEX."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from forgex.agents.nodes.coder import CoderNode
from forgex.agents.nodes.planner import PlannerNode
from forgex.agents.nodes.reviewer import ReviewerNode
from forgex.agents.nodes.tester import TesterNode
from forgex.core.orchestrator import ForgexState, WorkflowOrchestrator

DEFAULT_AGENT_WORKFLOW = (
    "planner",
    "coder",
    "reviewer",
    "tester",
)


@dataclass(slots=True)
class AgentWorkflowConfig:
    """Configuration for constructing the default agent workflow."""

    max_review_cycles: int = 1
    max_test_cycles: int = 1
    include_tester: bool = True


def build_default_agent_workflow(
    orchestrator: WorkflowOrchestrator,
    *,
    model: Any = None,
    config: AgentWorkflowConfig | None = None,
) -> WorkflowOrchestrator:
    """Register and connect the default planner->coder->reviewer(->tester) workflow."""

    cfg = config or AgentWorkflowConfig()
    if cfg.max_review_cycles < 0:
        raise ValueError("max_review_cycles must be >= 0.")
    if cfg.max_test_cycles < 0:
        raise ValueError("max_test_cycles must be >= 0.")

    planner = PlannerNode(model=model)
    coder = CoderNode(model=model)
    reviewer = ReviewerNode(model=model)
    tester = TesterNode(model=model)

    orchestrator.register_node("planner", planner)
    orchestrator.register_node("coder", coder)
    orchestrator.register_node("reviewer", reviewer)
    if cfg.include_tester:
        orchestrator.register_node("tester", tester)

    orchestrator.set_entry_point("planner")
    orchestrator.add_edge("planner", "coder")
    orchestrator.add_edge("coder", "reviewer")

    def route_after_review(state: ForgexState) -> str:
        review = state.get("review") or {}
        metadata = state.get("metadata") or {}
        cycles = int(metadata.get("review_cycles", 0))
        approved = bool(review.get("approved", False))
        if not approved and cycles < cfg.max_review_cycles:
            state_metadata = dict(metadata)
            state_metadata["review_cycles"] = cycles + 1
            state["metadata"] = state_metadata
            return "coder"
        if cfg.include_tester:
            return "tester"
        return "__end__"

    review_routes = {"coder": "coder", "__end__": "__end__"}
    if cfg.include_tester:
        review_routes["tester"] = "tester"
    orchestrator.add_conditional_edges("reviewer", route_after_review, review_routes)

    if cfg.include_tester:
        def route_after_test(state: ForgexState) -> str:
            report = state.get("test_report") or {}
            metadata = state.get("metadata") or {}
            cycles = int(metadata.get("test_cycles", 0))
            verified = bool(report.get("verified", False))
            next_action = str(report.get("next_action", "complete")).lower()
            if (not verified or next_action in {"fix", "retest"}) and cycles < cfg.max_test_cycles:
                state_metadata = dict(metadata)
                state_metadata["test_cycles"] = cycles + 1
                state["metadata"] = state_metadata
                return "coder"
            return "__end__"

        orchestrator.add_conditional_edges(
            "tester",
            route_after_test,
            {"coder": "coder", "__end__": "__end__"},
        )
        orchestrator.set_finish_point("tester")
    else:
        orchestrator.set_finish_point("reviewer")

    return orchestrator


def register_default_agent_workflow(
    application: Any,
    *,
    model: Any = None,
    config: AgentWorkflowConfig | None = None,
) -> Any:
    """Configure the default workflow on a ForgexApplication-like object."""

    orchestrator = getattr(application, "orchestrator", None)
    if orchestrator is None:
        raise TypeError("application must provide an 'orchestrator' attribute.")
    if not isinstance(orchestrator, WorkflowOrchestrator):
        raise TypeError("application.orchestrator must be a WorkflowOrchestrator.")

    build_default_agent_workflow(
        orchestrator,
        model=model,
        config=config,
    )
    return orchestrator


__all__ = [
    "DEFAULT_AGENT_WORKFLOW",
    "AgentWorkflowConfig",
    "build_default_agent_workflow",
    "register_default_agent_workflow",
]
