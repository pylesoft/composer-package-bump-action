#!/usr/bin/env bash

set -euo pipefail

if grep -F "composer update \$PACKAGES_TO_UPDATE --with-all-dependencies --no-install --no-scripts" action.yml > /dev/null \
    && grep -F "composer update --with-all-dependencies --no-install --no-scripts" action.yml > /dev/null \
    && grep -F "Scoped update failed, retrying with a full composer.lock rebuild" action.yml > /dev/null \
    && grep -F "Validating bumped package versions in composer.lock" action.yml > /dev/null \
    && grep -F "composer show --locked --format=json" action.yml > /dev/null; then
    echo "PASS: composer.lock update validates bumped packages after scoped or full rebuild"
    exit 0
fi

echo "FAIL: composer.lock update is missing the scoped/full fallback or post-update package validation" >&2
exit 1
