#!/bin/sh
# Run from the repository root with PYTHON pointing to a test-enabled venv.
set -eu
PYTHON=${PYTHON:-python3}
repo=$(pwd)
work=$(mktemp -d "${TMPDIR:-/tmp}/tightarray-sanitize.XXXXXX")
trap 'rm -rf "$work"' EXIT
TIGHTARRAY_SANITIZE=1 "$PYTHON" setup.py build_ext --force --build-temp "$work/objects" --build-lib "$work/lib"
cp tightarray/*.py tightarray/*.pyi tightarray/py.typed "$work/lib/tightarray/"
mkdir -p "$work/lib/tightarray/array_api"
cp tightarray/array_api/*.py tightarray/array_api/*.pyi "$work/lib/tightarray/array_api/"
mkdir -p "$work/lib/examples"
cp examples/lattice.py "$work/lib/examples/"
runtime=$(clang --print-resource-dir)/lib/darwin/libclang_rt.asan_osx_dynamic.dylib
test -f "$runtime"
# Framework launchers can re-exec and drop DYLD variables. Use their real binary.
runtime_python=$("$PYTHON" -c 'import pathlib,sys; p=pathlib.Path(sys.base_prefix)/"Resources/Python.app/Contents/MacOS/Python"; print(p if p.is_file() else sys.executable)')
site_packages=$("$PYTHON" -c 'import sysconfig; print(sysconfig.get_path("purelib"))')
cd "$work/lib"
export DYLD_INSERT_LIBRARIES="$runtime"
export ASAN_OPTIONS=detect_leaks=0:halt_on_error=1
export UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1
export PYTHONPATH="$work/lib:$site_packages"
"$runtime_python" -c 'import tightarray._core, tightarray._numpy, pathlib; assert all(pathlib.Path(m.__file__).parent == pathlib.Path.cwd() / "tightarray" for m in (tightarray._core, tightarray._numpy))'
"$runtime_python" -m pytest "$repo/tests" -q
