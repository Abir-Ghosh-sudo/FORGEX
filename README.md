# FORGEX

**Build Beyond Code.**

A terminal-first autonomous AI coding agent for Python. Plan, code, review, test, and debug repositories autonomously using local AI models.

## Features

- Autonomous multi-step coding with Planner, Coder, Reviewer, and Tester agents
- Repository understanding and context assembly
- Local model inference: Ollama, llama.cpp, Transformers
- Hugging Face Hub model downloads (no hosted inference required)
- Terminal execution with permission controls and approvals
- Test execution and self-debugging
- Git branch, commit, rollback, and recovery
- Persistent memory with SQLite
- MCP client/server support
- Custom skills and plugins
- Windows and Linux support
- C++20 native acceleration (optional, via pybind11)

## Installation

```bash
git clone https://github.com/forgex-org/forgex.git
cd forgex
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate.bat
pip install -e ".[dev]"
forgex --version
forgex doctor
forgex init ./my-project
forgex chat
```

## Documentation

See `docs/` for installation, quick start, CLI reference, configuration, model setup, MCP, plugins, skills, architecture, and troubleshooting.

## License

Apache-2.0
