# SPIDER Operations Runbook

## Installation
1. Clone repository to `D:\PhanMem_Tools\SPIDER`.
2. Activate virtual environment `runtime\venv`.
3. Verify system health:
   ```powershell
   runtime\venv\Scripts\python.exe -m spider.cli.main doctor
   ```

## Running Investigations
For the browser UI, double-click `run_spider.bat`. It uses `runtime/venv/Scripts/python.exe`, binds only `127.0.0.1:8765`, checks `/api/health?ready=true`, and then opens the default browser. This readiness check verifies the database and backend PID; provider diagnostics remain available through `/api/health` and the Providers page.

Use `stop_spider.bat` to request graceful shutdown. `data/launcher.json` records the backend's own PID, Windows creation time, executable path and shutdown event. A stale PID or foreign process on port 8765 is left untouched. Concurrent launches are serialized by a Windows file lock. There is no process-name kill or forced-kill fallback. If shutdown takes longer than 45 seconds, inspect `data/launcher.log` and retry after pending work finishes.

Legacy manually started servers are not adopted automatically. Stop that exact server from its original console before using the new launcher. Do not use `taskkill /IM python.exe`.

API keys migrate automatically from `data/settings.json` to `data/api-keys.dpapi` before the web app starts. Keep both files local and out of Git. DPAPI decryption requires the same Windows user context; re-enter keys when moving to another account/machine. A corrupt or unavailable vault blocks startup/settings writes rather than falling back to plaintext. Do not copy secret values into diagnostics or handoffs.

Implementation references: [Microsoft DPAPI](https://learn.microsoft.com/en-us/windows/win32/seccrypto/example-c-program-using-cryptprotectdata), [Playwright local browser storage](https://playwright.dev/python/docs/browsers).

```powershell
# Passive domain investigation
runtime\venv\Scripts\python.exe -m spider.cli.main investigate example.com

# Authorized active investigation
runtime\venv\Scripts\python.exe -m spider.cli.main investigate example.com --authorized --profile active_authorized
```
