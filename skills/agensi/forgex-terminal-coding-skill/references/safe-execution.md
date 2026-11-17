# Safe execution checklist

Apply these rules before using filesystem, terminal, network, or Git capabilities.

## Workspace and files

- Resolve and confirm the workspace root before reading or writing.
- Keep task edits inside the selected workspace unless the user explicitly authorizes otherwise.
- Inspect a target file before replacing it. Prefer minimal patches over whole-file rewrites.
- Do not follow symlinks or paths that escape the workspace without explicit authorization and a clear reason.
- Treat deletion, bulk rename, recursive overwrite, and cleanup as destructive. Explain the impact and obtain approval first.
- Preserve untracked files and modifications that existed before the task.

## Terminal commands

- Prefer explicit argument arrays or structured command APIs over shell-string concatenation.
- Avoid interpolating untrusted input into shell commands.
- Explain commands that install packages, change system state, access networks, or consume significant resources.
- Ask before privileged commands, destructive commands, service restarts, database changes, deployment, or production access.
- Use timeouts and bounded output where supported.
- Never run opaque scripts from the internet without inspecting them and obtaining user approval.

## Secrets

- Do not read or disclose secret stores, private keys, credential files, or unrelated personal data.
- Redact tokens and credentials from logs and reports.
- Do not commit .env files, private keys, access tokens, or generated credential files.
- If a secret appears in output, do not repeat it; advise rotation if exposure may have occurred.

## Git

- Start with git status --short and inspect the current branch.
- Do not use git reset --hard, git clean -fd, forced checkout, or destructive history rewriting as routine cleanup.
- Do not stage the entire repository blindly. Stage only task-related paths.
- Review git diff and git diff --cached before committing.
- Do not commit or push unless explicitly requested.
- Never force-push without explicit, informed authorization.

## Verification and reporting

- Run project-defined checks, not invented commands.
- Distinguish test failure from environment/setup failure.
- Report exact checks run and observed outcomes.
- State clearly what was not tested.
