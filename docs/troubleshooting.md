# FORGEX Troubleshooting

## Common Issues

### `forgex` command not found

Activate the virtual environment:
```bash
# Windows
.venv\Scripts\activate.bat
# Linux
source .venv/bin/activate
```

### Native C++ build fails

FORGEX works without the native extension. For C++ acceleration:
- Windows: Install Visual Studio Build Tools with Desktop development with C++
- Linux: Install build-essential and cmake

### Ollama connection refused

Start Ollama:
```bash
ollama serve
```
Then pull a model:
```bash
ollama pull qwen2.5-coder:7b
```

### Model not found

Check available models:
```bash
forgex model list
```

### Permission denied on terminal commands

FORGEX requires approval for dangerous commands by default. Use `/approve` in chat or adjust security settings:
```
FORGEX_SECURITY__REQUIRE_COMMAND_APPROVAL=false
```

### Import errors

Install all dependencies:
```bash
pip install -e ".[dev]"
```

### Native module import fails

The `forgex._native` module is optional. FORGEX falls back to pure Python when unavailable.

## Support

- Check `forgex doctor` for diagnostics
- Review logs in `~/.forgex/logs/`
- File issues at the project repository