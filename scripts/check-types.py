"""Check consumer typing against wheel contents, outside the source checkout."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import zipfile

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='tightarray-types-') as directory:
    tmp = Path(directory)
    subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-deps',
                    '--no-build-isolation', '-w', str(tmp), str(root)], check=True)
    with zipfile.ZipFile(next(tmp.glob('*.whl'))) as wheel:
        required = {'tightarray/py.typed', 'tightarray/__init__.pyi',
                    'tightarray/array_api/__init__.pyi'}
        assert required <= set(wheel.namelist()), 'wheel omitted type information'
        wheel.extractall(tmp / 'wheel')
    env = dict(os.environ, MYPYPATH=str(tmp / 'wheel'))
    # Check stubs themselves, not only their imported use sites.
    subprocess.run([sys.executable, '-m', 'mypy', '--strict',
                    str(tmp / 'wheel/tightarray/__init__.pyi'),
                    str(tmp / 'wheel/tightarray/array_api/__init__.pyi')],
                   cwd=tmp, env=env, check=True)
    subprocess.run([sys.executable, '-m', 'mypy', '--strict',
                    str(root / 'tests/typing/usage.py')], cwd=tmp, env=env, check=True)
