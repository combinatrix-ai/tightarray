"""Keep declared public names and structured returns aligned with runtime."""
import ast
from pathlib import Path
import numpy as np
from tightarray import array_api as xp


def test_namespace_stub_covers_runtime_functions():
    path = Path(xp.__file__).with_suffix('.pyi')
    tree = ast.parse(path.read_text())
    functions = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert set(xp._FUNCTIONS) <= functions
    for name in functions:
        assert callable(getattr(xp, name)), name
    for cls, obj in [('_Linalg', xp.linalg), ('_FFT', xp.fft)]:
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls)
        for method in node.body:
            if isinstance(method, ast.FunctionDef):
                assert callable(getattr(obj, method.name)), method.name


def test_declared_structured_results():
    x = xp.asarray([[2., 0.], [0., 3.]])
    for result, fields in [
        (xp.unique_all(x), ('values', 'indices', 'inverse_indices', 'counts')),
        (xp.unique_counts(x), ('values', 'counts')),
        (xp.unique_inverse(x), ('values', 'inverse_indices')),
        (xp.linalg.eigh(x), ('eigenvalues', 'eigenvectors')),
        (xp.linalg.qr(x), ('Q', 'R')),
        (xp.linalg.slogdet(x), ('sign', 'logabsdet')),
        (xp.linalg.svd(x), ('U', 'S', 'Vh')),
    ]:
        assert result._fields == fields
        assert all(isinstance(getattr(result, field), xp.Array) for field in fields)
    assert isinstance(xp.fft.fft(x), xp.Array)
    assert isinstance(xp.can_cast(xp.uint8, xp.uint16), bool)
    assert isinstance(xp.broadcast_shapes((2, 1), (3,)), tuple)
