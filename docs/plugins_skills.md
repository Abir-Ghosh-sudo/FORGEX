# FORGEX Plugin and Skill Documentation

## Skills

Skills are task-specific capabilities that agents can invoke.

### Builtin Skills

| Skill | Description |
|---|---|
| coding | Code generation and editing |
| debugging | Error analysis and fix suggestions |
| testing | Test discovery and verification |
| refactoring | Code improvement suggestions |

### Using Skills

```python
from forgex.skills.registry import SkillRegistry
from forgex.skills.base import SkillContext

registry = SkillRegistry()
# Skills auto-register from builtin modules
result = await registry.execute("coding", SkillContext(
    workspace="./my-project",
    task="Create a hello world function",
    files=["hello.py"],
))
```

## Plugins

Plugins extend FORGEX with custom functionality.

### Plugin Interface

```python
from forgex.plugins.base import Plugin, PluginContext, PluginResult

class MyPlugin(Plugin):
    name = "my-plugin"
    version = "1.0.0"

    async def initialize(self, context: PluginContext) -> PluginResult:
        return PluginResult(success=True, output="initialized")

    async def shutdown(self) -> PluginResult:
        return PluginResult(success=True, output="shutdown")

    async def execute(self, action: str, params: dict) -> PluginResult:
        return PluginResult(success=True, output=f"executed {action}")
```

### Plugin Registry

```python
from forgex.plugins.registry import PluginRegistry
from forgex.plugins.base import PluginContext

registry = PluginRegistry()
registry.register(MyPlugin)
plugin = registry.create_instance("my-plugin", PluginContext(workspace="."))
result = await plugin.execute("do-something", {})
```

### Plugin Loader

Load from entry points or directories:

```python
from forgex.plugins.loader import PluginLoader

loader = PluginLoader(registry)
loader.load_from_entry_points("forgex.plugins")
loader.load_from_directory("./plugins")
```
