"""Derive a typed namespace protocol from public signatures; --check detects drift."""
import ast
from pathlib import Path
import sys

path = Path(__file__).resolve().parents[1] / 'tightarray/array_api/__init__.pyi'
marker = '# Generated namespace protocol: scripts/generate-namespace-stub.py\n'
original = path.read_text()
source = original.split(marker)[0].rstrip() + '\n\n'
lines = source.splitlines()
body = [marker, 'class _Namespace(Protocol):\n']
for node in ast.parse(source).body:
    if isinstance(node, ast.FunctionDef) and (not node.name.startswith('_') or node.name == '__array_namespace_info__'):
        for decorator in node.decorator_list:
            body.append('    @' + ast.unparse(decorator) + '\n')
        body.append('    @staticmethod\n')
        body.extend('    ' + line + '\n' for line in lines[node.lineno-1:node.end_lineno])
for name in ['bool', 'uint8', 'uint16', 'uint32', 'uint64', 'int8', 'int16',
             'int32', 'int64', 'float32', 'float64', 'complex64', 'complex128']:
    body += ['    @property\n', f'    def {name}(self) -> type[np.{name}]: ...\n']
for name, typ in [('linalg', '_Linalg'), ('fft', '_FFT'), ('e', 'float'), ('pi', 'float'),
                  ('inf', 'float'), ('nan', 'float'), ('newaxis', 'None'),
                  ('__array_api_version__', 'str'), ('__version__', 'str'),
                  ('StorageWideningWarning', 'type[StorageWideningWarning]'),
                  ('StorageWideningError', 'type[StorageWideningError]')]:
    body += ['    @property\n', f'    def {name}(self) -> {typ}: ...\n']
body += ['    @staticmethod\n    def set_strict(enabled: _b.bool = ...) -> None: ...\n',
         '    @staticmethod\n    def strict(enabled: _b.bool = ...) -> AbstractContextManager[None]: ...\n']
result = source + ''.join(body)
if '--check' in sys.argv:
    if result != original:
        raise SystemExit('namespace protocol is stale; run scripts/generate-namespace-stub.py')
else:
    path.write_text(result)
