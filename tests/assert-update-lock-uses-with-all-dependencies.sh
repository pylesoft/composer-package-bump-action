#!/usr/bin/env bash

set -euo pipefail

if grep -F "composer update \$PACKAGES_TO_UPDATE --with-all-dependencies --no-install --no-scripts" action.yml > /dev/null \
    && grep -F "composer update --with-all-dependencies --no-install --no-scripts" action.yml > /dev/null \
    && grep -F "Scoped update failed, retrying with a full composer.lock rebuild" action.yml > /dev/null; then
    echo "PASS: composer.lock update tries scoped packages first and falls back to a full rebuild"
    exit 0
fi

echo "FAIL: composer.lock update does not implement the scoped-then-full fallback" >&2
exit 1
