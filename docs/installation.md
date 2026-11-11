# FORGEX Installation Guide

## Requirements

- Python 3.11+
- Windows or Linux
- Optional: Ollama, llama-cpp-python, transformers, torch
- Optional: MSVC Build Tools (Windows) or build-essential (Linux) for native C++

## One-Command Install

```bash
# Clone or download FORGEX
cd forgex

# Create venv and install
python -m venv .venv
# Windows:
.venv\Scripts\activate.bat
# Linux/macOS:
source .venv/bin/activate

# Install FORGEX
pip install -e ".[dev]"

# Verify
forgex --version
forgex doctor
```

## Windows Installer

```powershell
python installers/windows/install.py
```

## Linux Installer

```bash
python installers/linux/install.py
```

## Optional Model Providers

### Ollama (recommended)
```bash
# Install Ollama from https://ollama.com
ollama pull qwen2.5-coder:7b
forgex model list
forgex model status
```

### llama.cpp (GGUF)
```bash
pip install llama-cpp-python
# Download a GGUF model to ./models/
forgex model use llama_cpp ./models/model.gguf
```

### Transformers
```bash
pip install "forgex-ai[transformers]"
# Download from Hugging Face
forgex model download Qwen/Qwen2.5-Coder-7B-Instruct
forgex model use transformers ./models/Qwen2.5-Coder-7B-Instruct
```

## Native C++ Build (optional)

```bash
# Requires MSVC Build Tools (Windows) or build-essential (Linux)
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
cmake --install build --config Release
python -c "import forgex._native as n; print(n.native_capabilities())"
```
