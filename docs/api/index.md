# FORGEX API Documentation

## Core API

### ForgexApplication

Main application composition root.

```python
from forgex.core.application import ForgexApplication

app = ForgexApplication(workspace="./my-project")
await app.start()
result = await app.execute_task(task)
await app.shutdown()
```

### WorkflowOrchestrator

LangGraph workflow orchestrator.

```python
from forgex.core.orchestrator import WorkflowOrchestrator
from forgex.core.task import TaskManager
from forgex.core.events import EventBus

event_bus = EventBus()
task_manager = TaskManager(event_bus)
orchestrator = WorkflowOrchestrator(task_manager, workspace=Path("."))
```

## Model API

### ModelManager

Unified model management.

```python
from forgex.models.manager import ModelManager

manager = ModelManager()
provider = manager.get_provider()
result = manager.generate([{"role": "user", "content": "Hello"}])
```

### Providers

- OllamaProvider
- LlamaCppProvider
- TransformersProvider

## Context API

### ContextManager

Repository context gathering.

```python
from forgex.context.context_manager import ContextManager

ctx = ContextManager("./my-project")
snapshot = ctx.gather_context(task="Add feature X")
```

## Memory API

### SQLiteMemoryStore

Persistent memory storage.

```python
from forgex.memory.sqlite_store import SQLiteMemoryStore
from forgex.memory.memory_store import MemoryItem

store = SQLiteMemoryStore("~/.forgex/memory.db")
await store.add(MemoryItem(id="1", content="Hello", memory_type="conversation"))
results = await store.search("Hello", limit=5)
```

## Tools API

### FilesystemToolkit

```python
from forgex.tools.filesystem import FilesystemToolkit
from forgex.tools.filesystem.workspace import WorkspaceService

ws = WorkspaceService(workspace="./my-project")
toolkit = FilesystemToolkit(ws)
result = toolkit.read_file("README.md")
```

### TestingToolkit

```python
from forgex.tools.testing import TestingToolkit
from forgex.runtime.supervisor import ProcessSupervisor

supervisor = ProcessSupervisor()
toolkit = TestingToolkit(workspace="./my-project", supervisor=supervisor)
result = await toolkit.run_tests()
```

## Security API

Permission-based security controls integrated throughout the system.

## Exceptions

All FORGEX exceptions inherit from `ForgexError`:
- `ConfigurationError`, `InitializationError`, `ExecutionError`
- `AgentError`, `ModelError`, `ToolExecutionError`
- `SecurityError`, `PermissionDeniedError`
- `SessionError`, `StorageError`, `ContextError`
- `TaskCancelledError`
