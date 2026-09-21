"""Check consumer typing against wheel contents, outside the source checkout."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import zipfile

root = Path(__file__).resolve().parents[1]
subprocess.run([sys.executable, str(root / 'scripts/generate-namespace-stub.py'), '--check'], check=True)
with tempfile.TemporaryDirectory(prefix='tightarray-types-') as directory:
    tmp = Path(directory)
    subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-deps',
                    '--no-build-isolation', '-w', str(tmp), str(root)], check=True)
    with zipfile.ZipFile(next(tmp.glob('*.whl'))) as wheel:
        required = {'tightarray/py.typed', 'tightarray/__init__.pyi',
                    'tightarray/array_api/__init__.pyi', 'tightarray/numba.pyi',
                    'tightarray/compressed.pyi'}
        assert required <= set(wheel.namelist()), 'wheel omitted type information'
        wheel.extractall(tmp / 'wheel')
    env = dict(os.environ, MYPYPATH=str(tmp / 'wheel'))
    # Forbid explicit dynamic escape hatches in the distributed type contract.
    import ast
    for path in (tmp / 'wheel/tightarray').rglob('*.pyi'):
        tree = ast.parse(path.read_text())
        assert not any((isinstance(n, ast.Name) and n.id == 'Any') or
                       (isinstance(n, ast.Attribute) and n.attr == 'Any') or
                       (isinstance(n, ast.alias) and n.name == 'Any') for n in ast.walk(tree)), path
    # Check stubs themselves, not only their imported use sites.
    subprocess.run([sys.executable, '-m', 'mypy', '--strict',
                    str(tmp / 'wheel/tightarray/__init__.pyi'),
                    str(tmp / 'wheel/tightarray/array_api/__init__.pyi'),
                    str(tmp / 'wheel/tightarray/numba.pyi'),
                    str(tmp / 'wheel/tightarray/compressed.pyi')],
                   cwd=tmp, env=env, check=True)
    subprocess.run([sys.executable, '-m', 'mypy', '--strict',
                    *[str(p) for p in sorted((root / 'tests/typing').glob('*.py'))]], cwd=tmp, env=env, check=True)

    subprocess.run([sys.executable, '-m', 'mypy', '--strict', '--disallow-any-expr',
                    str(root / 'tests/typing/no_any.py'),
                    str(root / 'tests/typing/numba_access.py'),
                    str(root / 'tests/typing/compressed_storage.py')], cwd=tmp, env=env, check=True)
