# SPIDER Threat Model & Security Considerations

## 1. Command Injection
- **Threat**: Malicious target strings containing shell metacharacters (e.g. `example.com; calc.exe`).
- **Defense**: Strict use of `asyncio.create_subprocess_exec()` with argument arrays; `shell=False`.

## 2. Path Traversal
- **Threat**: Crafting target names or artifact IDs containing `../` to overwrite system files.
- **Defense**: All artifact paths are sanitized and scoped inside `data/runs/<run-id>/`.

## 3. Secret Leakage
- **Threat**: Leaking API keys in logs, stdout, or Git.
- **Defense**: Separation of secrets from code, strict `.gitignore`, redaction of keys in diagnostics.
