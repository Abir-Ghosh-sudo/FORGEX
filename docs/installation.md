# FORGEX Installation Guide

## Recommended: one-command full setup

The installer creates an isolated Python environment, installs FORGEX and its required dependencies, then (with `--with-ollama`) installs Ollama, downloads the lightweight `qwen2.5-coder:1.5b` model, and selects it automatically.

### Windows 10/11 (PowerShell)
```powershell
$s = irm https://raw.githubusercontent.com/Abir-Ghosh-sudo/FORGEX/main/install.ps1; & ([scriptblock]::Create($s)) -WithOllama
```

Requires Python 3.11+, internet access, and `winget`.

### Linux (Bash)
```bash
curl -fsSL https://raw.githubusercontent.com/Abir-Ghosh-sudo/FORGEX/main/install.sh | bash -s -- --with-ollama
```

Requires Python 3.11+, curl, internet access, and sudo permission for the official Ollama installer.

## Verify and start

Open a new terminal if needed:
```bash
forgex --version
forgex doctor
forgex model status
forgex chat
```

From a project directory:
```bash
forgex init
forgex analyze
forgex run "Explain this codebase"
```

## FORGEX only (Ollama already installed)

Windows:
```powershell
irm https://raw.githubusercontent.com/Abir-Ghosh-sudo/FORGEX/main/install.ps1 | iex
```

Linux:
```bash
curl -fsSL https://raw.githubusercontent.com/Abir-Ghosh-sudo/FORGEX/main/install.sh | bash
```

Then install/select the default model once:
```bash
ollama pull qwen2.5-coder:1.5b
forgex model use ollama qwen2.5-coder:1.5b
```

## Optional integrations

These are not needed for the standard Ollama workflow:
```bash
pip install "forgex-ai[transformers]"  # Hugging Face Transformers
pip install "forgex-ai[mcp]"           # Model Context Protocol
pip install "forgex-ai[vector]"         # Vector-store support
pip install llama-cpp-python             # llama.cpp / GGUF
```

## Optional native C++ build

The pure-Python engine works without a compiler. For native acceleration, install a C++20 toolchain, CMake, Ninja, and pybind11, then follow the build instructions in the main README.

## Notes

- The model download is large and needs internet access; it is not bundled with the Python package.
- Local inference uses CPU/RAM while generating. The 1.5B model is the lightweight default, but it still consumes system resources.
- The installer updates the FORGEX installation directory. Back up local modifications inside that directory before rerunning it.
