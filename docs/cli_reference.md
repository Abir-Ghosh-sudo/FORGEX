# FORGEX CLI Reference

## Global Commands

```
forgex --version        Show version
forgex doctor           Run diagnostics
forgex init             Initialize a project
forgex chat             Start interactive chat
forgex run              Run an autonomous coding task
forgex analyze          Analyze repository
forgex test             Run tests
forgex config           Manage configuration
forgex git              Git operations
forgex session          Session management
forgex model            Model management
forgex update           Check for updates
```

## Model Commands

```
forgex model status     Show model configuration
forgex model list       List available Ollama models
forgex model pull <name> Pull a model from Ollama
forgex model use <provider> <model> Set active model
forgex model download <repo-id> Download from Hugging Face Hub
forgex model inspect <name> Inspect a model
```

## Git Commands

```
forgex git status       Show Git status
forgex git init         Initialize Git repo
```

## Session Commands

```
forgex session list     List sessions
```

## Slash Commands (chat only)

```
/help, /clear, /exit, /status, /model, /plan, /approve, /reject, /context, /compact, /tools, /skills
```
