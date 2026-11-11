# FORGEX Architecture

## Overview

FORGEX is a terminal-first autonomous AI coding agent with a modular architecture.

### Core Components

| Component | Responsibility |
|---|---|
| Core | Application lifecycle, task management, event bus, orchestrator |
| Config | Pydantic-based settings management |
| Agents | Planner, coder, reviewer, tester with LangGraph orchestration |
| Models | Local model providers, routing, hardware detection, context budgeting |
| Context | Repository understanding, file/symbol retrieval, context assembly |
| Tools | Filesystem, terminal, git, testing, packages |
| Memory | Persistent SQLite memory with retrieval |
| MCP | Model Context Protocol client/server |
| Skills | Builtin and custom skills |
| Plugins | Plugin system with permissions |
| Verification | Code, change, and result verification |
| Git | Safe Git operations with rollback |
| Security | Permissions, policies, approvals, sandboxing |

### Agent Workflow

```
User Request → Planner → Coder → Reviewer → Tester → Git Checkpoint → Final Report
       ↑                                                      |
       └────────── Failed Tests → Debug → Coder ←─────────────┘
```

### Data Flow

1. CLI receives user request
2. Application core creates task and workflow
3. Context engine gathers repository context
4. Planner agent creates execution plan
5. Coder agent implements changes via tools
6. Tester agent runs tests
7. Reviewer agent reviews changes
8. Git checkpoint (optional)
9. Final report to user

## Technology Stack

- Python 3.11+
- Typer (CLI), Rich (terminal UI)
- Pydantic (configuration)
- LangChain + LangGraph (agent orchestration)
- SQLite (persistent storage)
- Hugging Face Hub (model downloads)
- Ollama / llama.cpp / Transformers (local inference)
- Tree-sitter (code parsing)
- MCP (external tool integration)
- GitPython (Git integration)
- pybind11 + C++20 (native acceleration, optional)
