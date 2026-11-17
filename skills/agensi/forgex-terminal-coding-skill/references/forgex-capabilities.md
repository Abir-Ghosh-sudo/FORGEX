# FORGEX capability map

This reference summarizes the FORGEX repository architecture and documented interfaces. It is context for agents using the skill; it is not a promise that every feature is enabled in every installation.

## Documented agent workflow

1. The CLI receives a user task.
2. The application core creates the task and workflow.
3. The context engine gathers repository context.
4. Planner creates an execution plan.
5. Coder implements changes through tools.
6. Tester runs tests.
7. Reviewer reviews changes.
8. An optional Git checkpoint is created.
9. The agent returns a final report.

Failed tests can route work back through debugging and coding.

## Capability areas

| Area | Repository location | Responsibility |
|---|---|---|
| Agent roles and workflow | src/forgex/agents/ | Planner, coder, reviewer, tester and orchestration |
| Repository context | src/forgex/context/ | File and symbol retrieval, context assembly |
| Filesystem tools | src/forgex/tools/filesystem/ | Workspace-scoped reads, writes, search and directory inspection |
| Terminal tools | src/forgex/tools/terminal/ | Terminal requests through authorization and runner layers |
| Testing tools | src/forgex/tools/testing/ | Framework detection, test execution, parsing and coverage |
| Git operations | src/forgex/tools/git/, src/forgex/git/ | Repository operations and safety helpers |
| Security | src/forgex/security/, src/forgex/runtime/security.py | Policies, permissions, approvals, sandbox and audit |
| Native skills | src/forgex/skills/ | FORGEX skill interface and registry |
| CLI | src/forgex/cli/ | User-facing commands |

## Documented CLI commands

The CLI reference lists forgex doctor (diagnostics), forgex init (initialize a project), forgex analyze (analyze a repository), forgex run (autonomous coding task), forgex test (run tests), forgex git status (inspect Git status), and forgex session list (list sessions).

Check the installed version's help before relying on command options. Do not assume a command is installed or configured.

## Native skill interface

The repository documents a Python skill interface based on Skill, SkillContext, SkillResult, and SkillRegistry. A native FORGEX skill is not the same as this portable Agensi SKILL.md package. This package does not register itself with FORGEX or change its runtime.

## Source of truth

For implementation details, inspect the checked-out version of the files above and current repository documentation. This reference is a navigation aid, not a substitute for source inspection.
