#!/usr/bin/env bash

set -euo pipefail

if grep -F "composer update \$PACKAGES_TO_UPDATE" action.yml | grep -Eq -- '--with-all-dependencies|-W'; then
    echo "PASS: composer update allows transitive dependency changes"
    exit 0
fi

echo "FAIL: composer update does not allow transitive dependency changes" >&2
exit 1
