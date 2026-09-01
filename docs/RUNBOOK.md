# SPIDER Operations Runbook

## Installation
1. Clone repository to `D:\PhanMem_Tools\SPIDER`.
2. Activate virtual environment `runtime\venv`.
3. Verify system health:
   ```powershell
   runtime\venv\Scripts\python.exe -m spider.cli.main doctor
   ```

## Running Investigations
```powershell
# Passive domain investigation
runtime\venv\Scripts\python.exe -m spider.cli.main investigate example.com

# Authorized active investigation
runtime\venv\Scripts\python.exe -m spider.cli.main investigate example.com --authorized --profile active_authorized
```
