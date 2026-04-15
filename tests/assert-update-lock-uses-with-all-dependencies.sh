#!/usr/bin/env bash

set -euo pipefail

if grep -F "composer update --with-all-dependencies --no-install --no-scripts" action.yml > /dev/null; then
    echo "PASS: composer.lock is rebuilt without scoping the update to selected packages"
    exit 0
fi

echo "FAIL: composer.lock rebuild is still scoped to selected packages" >&2
exit 1
