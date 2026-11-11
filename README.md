# FORGEX

**Build Beyond Code.**

[![CI](https://github.com/Abir-Ghosh-sudo/FORGEX/actions/workflows/ci.yml/badge.svg)](https://github.com/Abir-Ghosh-sudo/FORGEX/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-1.0.0--stable-blue.svg)](https://github.com/Abir-Ghosh-sudo/FORGEX)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-brightgreen.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-Apache--2.0-green.svg)](LICENSE)

A terminal-first autonomous AI coding agent. Plan, code, review, test, and debug repositories autonomously using local models or custom APIs with strict permission gates and human-in-the-loop approval.

---

## Key Features

- **Autonomous Multi-Agent Workflow:** Planner, Coder, Reviewer, and Tester agents collaborating via LangGraph with bounded cycle loops and verification guards.
- **Compiler-Free Pure-Python Core:** Installs effortlessly without any C++ compiler or native toolchain requirements.
- **Optional C++20 Native Acceleration:** High-performance indexing, AST parsing, and fuzzy searching via pybind11 when build tools are available.
- **Local Model First:** Native integration with Ollama (`llama3.1`, `qwen2.5-coder`), GGUF (`llama.cpp`), and Hugging Face Hub (offline & cached).
- **Security & Approvals:** Granular permission system, command audit logging, risk scoring, null-byte prevention, and interactive confirmation for filesystem and terminal modifications.
- **Extensible:** Model Context Protocol (MCP) client/server, custom skills (`coding`, `debugging`, `refactoring`, `testing`), and dynamic plugin loading.
- **Cross-Platform:** Full compatibility with Windows 11/10 and Linux.

---

## Quick Start

### 1. Pure Python Installation (Default, No Compiler Needed)

```bash
git clone https://github.com/Abir-Ghosh-sudo/FORGEX.git
cd FORGEX

python -m venv .venv

# On Windows:
.venv\Scripts\activate.bat
# On Linux/macOS:
source .venv/bin/activate

pip install -e ".[dev]"
```

### 2. Optional C++20 Native Acceleration (For maximum performance)

```bash
# Install native build dependencies
pip install pybind11 cmake ninja

# Build native extension
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DFORGEX_BUILD_PYTHON=ON
cmake --build build --config Release
```

### 3. Verify Environment

```bash
forgex --version
forgex doctor
```

`forgex doctor` verifies Python, Git, Ollama connectivity, and native engine status.

---

## CLI Usage

| Command | Description |
|---|---|
| `forgex doctor` | Run system diagnostics and verify dependencies. |
| `forgex analyze [PATH]` | Inspect project language breakdown and file structure. |
| `forgex init [PATH]` | Initialize a FORGEX configuration in a target project. |
| `forgex run "TASK"` | Run an autonomous multi-step coding task on the current workspace. |
| `forgex chat` | Launch an interactive REPL coding session. |
| `forgex test run` | Discover and run test suites. |
| `forgex model list` | Manage and inspect local LLMs via Ollama. |
| `forgex git status` | View git status, changes, and diffs. |
| `forgex config show` | View current sanitized settings. |

---

## Architecture

FORGEX follows a stateful multi-agent architecture:

```
[ User Prompt ]
       │
       ▼
[ Planner Node ] ──> Decomposes task into atomic implementation steps
       │
       ▼
 [ Coder Node ]  ──> Executes file modifications & generates diffs
       │
       ▼
[ Reviewer Node ]──> Validates code quality, syntax, and risks
       │
   (Approved)
       ▼
 [ Tester Node ] ──> Executes tests, collects results & verifies fixes
       │
       ▼
[ Git & Output ] ──> Commits verified changes or surfaces human approvals
```

---

## Documentation

Full guides and references are available in [`docs/`](docs/):
- [`docs/quickstart.md`](docs/quickstart.md) - Quickstart walkthrough
- [`docs/architecture.md`](docs/architecture.md) - Deep architectural dive
- [`docs/cli_reference.md`](docs/cli_reference.md) - Comprehensive CLI flags and subcommands
- [`docs/configuration.md`](docs/configuration.md) - Configuration schema and settings
- [`docs/model_setup.md`](docs/model_setup.md) - Ollama, GGUF, and Hugging Face guide
- [`docs/mcp.md`](docs/mcp.md) - Model Context Protocol usage
- [`docs/plugins_skills.md`](docs/plugins_skills.md) - Custom skills and plugin authoring

---

## Testing

```bash
# Run complete test suite (520+ tests)
pytest tests

# Verify native engine tests
pytest tests/unit/test_native_engine.py

# Verify end-to-end coding agent workflow
pytest tests/e2e/test_end_to_end_workflow.py
```

---

## License

FORGEX is open-source software licensed under the [Apache-2.0 License](LICENSE).
