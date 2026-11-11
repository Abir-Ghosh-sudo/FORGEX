# FORGEX Configuration Reference

Configuration is managed via environment variables with `FORGEX_` prefix and nested `__` delimiter, or a `.env` file.

## Application Settings

| Variable | Default | Description |
|---|---|---|
| FORGEX_APP__NAME | FORGEX | Application name |
| FORGEX_APP__VERSION | 1.0.0 | Version |
| FORGEX_APP__ENVIRONMENT | development | Environment |
| FORGEX_APP__DEBUG | false | Debug mode |
| FORGEX_APP__WORKSPACE | null | Workspace path |

## Model Settings

| Variable | Default | Description |
|---|---|---|
| FORGEX_MODEL__PROVIDER | auto | ollama, llama_cpp, transformers |
| FORGEX_MODEL__MODEL_NAME | qwen2.5-coder:7b | Model name |
| FORGEX_MODEL__MODEL_PATH | null | Local model path |
| FORGEX_MODEL__OLLAMA_BASE_URL | http://127.0.0.1:11434 | Ollama URL |
| FORGEX_MODEL__CONTEXT_WINDOW | 8192 | Context window size |
| FORGEX_MODEL__MAX_OUTPUT_TOKENS | 2048 | Max output tokens |
| FORGEX_MODEL__TEMPERATURE | 0.2 | Temperature |
| FORGEX_MODEL__TOP_P | 0.95 | Top-p |
| FORGEX_MODEL__TRUST_REMOTE_CODE | false | Trust remote code |
| FORGEX_MODEL__LOCAL_FILES_ONLY | true | Local files only |

## Runtime Settings

| Variable | Default | Description |
|---|---|---|
| FORGEX_RUNTIME__MAX_CONCURRENCY | 1 | Max concurrent tasks |
| FORGEX_RUNTIME__COMMAND_TIMEOUT_SECONDS | 120 | Command timeout |
| FORGEX_RUNTIME__SHUTDOWN_TIMEOUT_SECONDS | 30 | Shutdown timeout |
| FORGEX_RUNTIME__MAX_CONTEXT_FILES | 100 | Max context files |
| FORGEX_RUNTIME__SEQUENTIAL_AGENTS | true | Sequential execution |

## Security Settings

| Variable | Default | Description |
|---|---|---|
| FORGEX_SECURITY__REQUIRE_COMMAND_APPROVAL | true | Require command approval |
| FORGEX_SECURITY__REQUIRE_FILE_WRITE_APPROVAL | false | Require file write approval |
| FORGEX_SECURITY__ALLOW_DESTRUCTIVE_COMMANDS | false | Allow destructive commands |
| FORGEX_SECURITY__ALLOW_NETWORK_ACCESS | false | Allow network access |
| FORGEX_SECURITY__RESTRICT_WORKSPACE_ACCESS | true | Restrict workspace |

## Storage Settings

| Variable | Default | Description |
|---|---|---|
| FORGEX_STORAGE__DATA_DIR | ~\.forgex\data | Data directory |
| FORGEX_STORAGE__DATABASE_NAME | forgex.db | Database name |
| FORGEX_STORAGE__ENABLE_BACKUPS | true | Enable backups |
| FORGEX_STORAGE__BACKUP_RETENTION_COUNT | 10 | Backup retention |

## MCP Settings

| Variable | Default | Description |
|---|---|---|
| FORGEX_MCP__ENABLED | false | Enable MCP |
| FORGEX_MCP__REQUEST_TIMEOUT_SECONDS | 30 | Request timeout |
| FORGEX_MCP__MAX_CONNECTIONS | 5 | Max connections |

## Telemetry Settings

| Variable | Default | Description |
|---|---|---|
| FORGEX_TELEMETRY__ENABLED | false | Enable telemetry |
| FORGEX_TELEMETRY__COLLECT_ERRORS | false | Collect errors |
| FORGEX_TELEMETRY__COLLECT_PERFORMANCE | false | Collect performance |
