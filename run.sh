#!/usr/bin/env bash
# stock_market_expert_bd — Universal Linux/macOS/POSIX Shell Launcher
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Pick python3 if present, else python
if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
else
    echo "Error: Python is not installed or not in PATH." >&2
    exit 1
fi

exec "$PYTHON" "$DIR/main.py" "$@"
