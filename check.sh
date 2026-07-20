#!/bin/bash
# Run all project checks (lint, format, type check, tests). Exits 0 iff all pass.

set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

status=0

run_check() {
    local name="$1"
    shift
    echo "=== $name ==="
    if "$@"; then
        echo "✓ $name passed"
    else
        echo "✗ $name failed"
        status=1
    fi
    echo ""
}

run_check "ruff check" ruff check .
run_check "ruff format" ruff format --check .
run_check "mypy" mypy ./
run_check "pytest" pytest

if [ "$status" -eq 0 ]; then
    echo "✅ All checks passed"
else
    echo "❌ Some checks failed"
fi

exit $status
