# Code Quality Tooling Changes

## Summary

Added `black` for automatic Python code formatting and created a development script for running quality checks.

---

## Files Changed

### `pyproject.toml`
- Added `[dependency-groups]` section with `black>=24.0.0` as a dev dependency
- Added `[tool.black]` configuration:
  - `line-length = 88` (black default)
  - `target-version = ["py313"]` (matches project's Python version)

### `scripts/quality.sh` (new file)
- Development script for running quality checks
- Usage:
  - `./scripts/quality.sh` — check formatting without making changes (CI-safe)
  - `./scripts/quality.sh --fix` — apply black formatting in-place

### Python files reformatted by black (9 files)
- `backend/models.py`
- `backend/app.py`
- `backend/rag_system.py`
- `backend/session_manager.py`
- `backend/search_tools.py`
- `backend/config.py`
- `backend/ai_generator.py`
- `backend/document_processor.py`
- `backend/vector_store.py`

---

## How to Use

Install dev dependencies (one-time):
```bash
uv sync --dev
```

Check formatting (no changes applied):
```bash
./scripts/quality.sh
```

Apply formatting:
```bash
./scripts/quality.sh --fix
```

Run black directly:
```bash
uv run black .          # format in-place
uv run black --check .  # check only
```
