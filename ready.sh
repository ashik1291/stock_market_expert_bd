#!/usr/bin/env bash
# stock_market_expert_bd — One-Click Unix/macOS Bootstrap
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
python3 "$DIR/scripts/bootstrap.py"
