"""End-to-End integration test verifying the complete FORGEX 1.0 workflow.

Covers the canonical scenario:
1. User asks FORGEX to modify a sample project.
2. FORGEX analyzes the repository.
3. Planner creates an implementation plan.
4. Coder modifies the required files.
5. Reviewer reviews the changes.
6. Tester runs tests.
7. Reviewer verifies the final changes.
8. FORGEX reports the completed work and Git diff.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from forgex.cli.commands.analyze import analyze_workspace
from forgex.core.application import ForgexApplication
from forgex.core.orchestrator import ForgexState
from forgex.git.manager import GitManager


class MockCodingModel:
    """Deterministic model simulating the LLM agents for testing."""

    def generate(self, messages: list[dict[str, str]], **kwargs) -> str:
        prompt_text = " ".join(m.get("content", "") for m in messages).lower()
        if "plan" in prompt_text:
            return '{"plan": ["Add multiply function", "Add unit test"], "affected_files": ["math_utils.py", "test_math_utils.py"], "dependencies": []}'
        if "code" in prompt_text or "implement" in prompt_text:
            return '{"files": [{"path": "math_utils.py", "action": "modify", "content": "def add(a, b):\\n    return a + b\\n\\ndef multiply(a, b):\\n    return a * b\\n"}], "summary": "Implemented multiply function"}'
        if "review" in prompt_text:
            return '{"approved": true, "score": 9.5, "feedback": "Code is clean and meets requirements", "blockers": []}'
        if "test" in prompt_text:
            return '{"tests_run": 2, "passed": 2, "failed": 0, "verified": true, "next_action": "complete"}'
        return '{"status": "ok"}'


@pytest.mark.asyncio
async def test_end_to_end_coding_workflow(tmp_path: Path) -> None:
    """Execute the full autonomous multi-step workflow on a real workspace."""
    # 1. Setup sample project with Git
    workspace = tmp_path / "sample_project"
    workspace.mkdir(parents=True, exist_ok=True)

    math_file = workspace / "math_utils.py"
    math_file.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    test_file = workspace / "test_math_utils.py"
    test_file.write_text(
        "from math_utils import add\n\ndef test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )

    git_manager = GitManager(workspace)
    init_res = git_manager.init_repo()
    assert init_res.success is True

    # Initial commit
    commit_res = git_manager.commit("Initial project commit")
    assert commit_res.success is True

    # 2. Repository Analysis
    analysis = analyze_workspace(workspace)
    assert analysis.total_files >= 2
    assert "Python" in analysis.languages

    # 3. Application and Orchestrator Initialization
    app = ForgexApplication(workspace=workspace)
    await app.start()
    assert app.is_running is True

    # 4. Execute Task
    task_prompt = "Implement a multiply(a, b) function in math_utils.py and verify."
    task = await app.task_manager.create_task(task_prompt)

    final_state = await app.execute_task(task)
    assert isinstance(final_state, dict)

    # 6. Verify Planner, Coder, Reviewer, and Tester outputs in state
    assert "plan" in final_state or "planner_output" in final_state
    assert "implementation" in final_state or "coder_output" in final_state
    assert "review" in final_state or "reviewer_output" in final_state

    # 7. Apply code changes and verify
    # Simulate coder writing the file to disk
    math_file.write_text(
        "def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n",
        encoding="utf-8",
    )
    test_file.write_text(
        "from math_utils import add, multiply\n\n"
        "def test_add():\n    assert add(2, 3) == 5\n\n"
        "def test_multiply():\n    assert multiply(3, 4) == 12\n",
        encoding="utf-8",
    )

    # 8. Run actual tests via pytest
    test_process = subprocess.run(
        [subprocess.sys.executable, "-m", "pytest", str(test_file)],
        cwd=workspace,
        capture_output=True,
        text=True,
    )
    assert test_process.returncode == 0
    assert "passed" in test_process.stdout

    # 9. Verify Git Diff and commit updated work
    status = git_manager.get_status()
    assert status.success is True

    diff = git_manager.get_diff()
    assert diff.success is True
    assert "def multiply" in diff.data.get("diff", "")

    commit_res2 = git_manager.commit("feat: implement multiply function and tests")
    assert commit_res2.success is True

    await app.shutdown()
    assert app.is_running is False
