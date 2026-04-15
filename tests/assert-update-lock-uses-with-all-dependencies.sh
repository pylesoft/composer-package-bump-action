#!/usr/bin/env bash

set -euo pipefail

if command -v python3 >/dev/null 2>&1; then
    python3 tests/action_behavior.py
else
    python tests/action_behavior.py
fi
