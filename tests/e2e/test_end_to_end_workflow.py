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
from forgex.git.manager import GitManager


class MockCodingModel:
    """Deterministic model simulating the LLM agents for testing."""

    def generate(self, messages: list[dict[str, str]], **kwargs) -> str:
        prompt_text = " ".join(m.get("content", "") for m in messages).lower()
        agent = str(kwargs.get("agent", "")).lower()
        if agent == "planner":
            return (
                '{"summary": "Implement multiply function", "steps": '
                '["Create multiply in math_utils.py", "Add unit test in test_math_utils.py"]}'
            )
        if agent == "coder":
            return (
                '{"summary": "Code changes completed", "actions": ['
                '{"type": "modify", "file": "math_utils.py", "content": '
                '"def add(a, b):\\n    return a + b\\n\\ndef multiply(a, b):\\n    return a * b\\n"},'
                '{"type": "modify", "file": "test_math_utils.py", "content": '
                '"from math_utils import add, multiply\\n\\ndef test_add():\\n    assert add(2, 3) == 5\\n\\ndef test_multiply():\\n    assert multiply(3, 4) == 12\\n"}'
                ']}'
            )
        if agent == "reviewer":
            return (
                '{"approved": true, "summary": "Code passes review without blockers", '
                '"findings": []}'
            )
        if agent == "tester":
            return (
                '{"summary": "All tests pass successfully", "verified": true, '
                '"next_action": "complete"}'
            )

        if "reviewer" in prompt_text:
            return (
                '{"approved": true, "summary": "Code passes review without blockers", '
                '"findings": []}'
            )
        if "tester" in prompt_text:
            return (
                '{"summary": "All tests pass successfully", "verified": true, '
                '"next_action": "complete"}'
            )
        if "coder" in prompt_text or "actions" in prompt_text:
            return (
                '{"summary": "Code changes completed", "actions": ['
                '{"type": "modify", "file": "math_utils.py", "content": '
                '"def add(a, b):\\n    return a + b\\n\\ndef multiply(a, b):\\n    return a * b\\n"},'
                '{"type": "modify", "file": "test_math_utils.py", "content": '
                '"from math_utils import add, multiply\\n\\ndef test_add():\\n    assert add(2, 3) == 5\\n\\ndef test_multiply():\\n    assert multiply(3, 4) == 12\\n"}'
                ']}'
            )
        return '{"summary": "Implement multiply function", "steps": ["step 1"]}'


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

    # Configure a deterministic identity for this isolated test repository.
    subprocess.run(
        ["git", "config", "user.name", "FORGEX Test"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "forgex-test@example.invalid"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )

    # Initial commit
    commit_res = git_manager.commit("Initial project commit")
    assert commit_res.success is True

    # 2. Repository Analysis
    analysis = analyze_workspace(workspace)
    assert analysis.total_files >= 2
    assert "Python" in analysis.languages

    # 3. Application and Orchestrator Initialization with deterministic mock model
    mock_model = MockCodingModel()
    app = ForgexApplication(
        workspace=workspace,
        model_manager=mock_model,
        file_approval_handler=lambda operation, target: True,
    )
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

    # 7. Verify CoderNode directly modified math_utils.py and test_math_utils.py on disk!
    math_content = math_file.read_text(encoding="utf-8")
    assert "def multiply(a, b):" in math_content
    test_content = test_file.read_text(encoding="utf-8")
    assert "def test_multiply():" in test_content
    assert "assert multiply(3, 4) == 12" in test_content

    # Verify implementation reported changed files
    implementation = final_state.get("implementation") or {}
    files_changed = implementation.get("files_changed") or []
    assert "math_utils.py" in files_changed
    assert "test_math_utils.py" in files_changed

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
