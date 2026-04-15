#!/bin/bash
# Development quality check script
# Usage:
#   ./scripts/quality.sh          - check formatting (no changes)
#   ./scripts/quality.sh --fix    - apply formatting in-place

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

run_check() {
    echo "Checking formatting with black..."
    uv run black --check .
    echo "All files are properly formatted."
}

run_fix() {
    echo "Applying black formatting..."
    uv run black .
    echo "Done."
}

case "${1:-}" in
    --fix)
        run_fix
        ;;
    "")
        run_check
        ;;
    *)
        echo "Usage: $0 [--fix]"
        echo "  (no args)  Check formatting without making changes"
        echo "  --fix      Apply black formatting to all Python files"
        exit 1
        ;;
esac
