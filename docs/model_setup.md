# FORGEX Model Setup

FORGEX 1.0 is local-first. No mandatory paid API or hosted inference service.

## Supported Providers

### Ollama (Recommended)

Ollama provides easy local model management.

```bash
# Install Ollama: https://ollama.com
ollama pull qwen2.5-coder:7b
forgex model use ollama qwen2.5-coder:7b
forgex model status
```

### llama.cpp (GGUF)

For quantized GGUF models on CPU/GPU.

```bash
pip install llama-cpp-python
forgex model use llama_cpp ./models/llama-model.gguf
```

### Transformers

For Hugging Face models running locally.

```bash
pip install "forgex-ai[transformers]"
forgex model download Qwen/Qwen2.5-Coder-7B-Instruct
forgex model use transformers ./models/Qwen2.5-Coder-7B-Instruct
```

### Hugging Face Hub Downloads

```bash
# Download model weights only (no hosted inference)
forgex model download Qwen/Qwen2.5-Coder-7B-Instruct
```

## Hardware-Aware Selection

FORGEX auto-detects hardware and recommends settings:

- <= 8GB RAM: 4K context, Q4_K_M quantization
- <= 16GB RAM: 8K context, Q4_K_M quantization, sequential agents
- <= 32GB RAM: 16K context, Q5_K_M quantization
- > 32GB RAM: 32K context, Q6_K_M quantization

## Offline Operation

Set `FORGEX_MODEL__LOCAL_FILES_ONLY=true` and use locally cached models.
