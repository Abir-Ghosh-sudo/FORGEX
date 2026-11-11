# FORGEX Quick Start

## 1. Initialize a Project

```bash
forgex init ./my-project --git
cd my-project
```

## 2. Configure a Model

```bash
# Check available models
forgex model list

# Set model
forgex model use ollama qwen2.5-coder:7b

# Check status
forgex model status
```

## 3. Start a Chat Session

```bash
forgex chat
```

## 4. Run an Autonomous Task

```bash
forgex run "Add a new API endpoint for user registration"
```

## 5. Analyze a Repository

```bash
forgex analyze
```

## Slash Commands (in chat)

```
/help    - Show available commands
/status  - Show task status
/model   - Show model config
/plan    - Show current plan
/approve - Approve pending action
/reject  - Reject pending action
/context - Show repository context
/tools   - List available tools
/skills  - List available skills
/clear   - Clear conversation
/exit    - Exit chat
```
