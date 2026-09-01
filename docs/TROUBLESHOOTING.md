# SPIDER Troubleshooting Guide

## Common Issues

### 1. `MISSING_CREDENTIAL` for Uncover
- **Symptom**: `spider doctor` displays `MISSING_CREDENTIAL` for uncover.
- **Cause**: No API keys configured in environment variables (e.g. `SHODAN_API_KEY`).
- **Solution**: Normal behavior for fresh installs. Set environment variables if access is required.

### 2. SQLite Database Locking
- **Cause**: Concurrent processes attempting raw SQLite writes.
- **Solution**: SPIDER uses `SingleDBWriter` and `WAL` mode. Ensure all writes go through `SpiderService`.
