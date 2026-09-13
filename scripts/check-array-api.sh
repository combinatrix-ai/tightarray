#!/bin/sh
# Pin the upstream suite and run its unmodified tests against tightarray's namespace.
set -eu
PYTHON=${PYTHON:-python3}
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
suite=${ARRAY_API_SUITE_DIR:-${TMPDIR:-/tmp}/tightarray-array-api-tests}
revision=ef5b39f1190d54dca0d9a12646033d2d123afdd5
if [ ! -d "$suite/.git" ]; then
    git clone --branch 2026.09.08 --depth 1 --recurse-submodules --shallow-submodules https://github.com/data-apis/array-api-tests.git "$suite"
fi
test "$(git -C "$suite" rev-parse HEAD)" = "$revision"
test -z "$(git -C "$suite" status --porcelain)"
test "$(git -C "$suite/array-api" rev-parse HEAD)" = 5f847a3858875c682ae901aa22b0413bf24be9da
export ARRAY_API_TESTS_MODULE=tightarray.array_api
export ARRAY_API_TESTS_VERSION=2025.12
export PYTHONPATH="$repo${PYTHONPATH:+:$PYTHONPATH}"
cd "$suite"
exec "$PYTHON" -m pytest array_api_tests --hypothesis-derandomize --max-examples=100 --xfails-file="$repo/tests/array-api-xfails.txt" "$@"
