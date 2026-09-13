# Static typing

The wheel ships public `.pyi` stubs and a `py.typed` marker following the
[Python typing distribution specification](https://typing.python.org/en/latest/spec/distributing.html).
Install `.[typecheck]` to run the pinned mypy checks, or use the wheel from a
consumer project with its own type checker.

```python
from tightarray import Array, Matrix
from tightarray import array_api as xp

a = Array([1, 2, 3], bits=2)
value: int = a[0]
part: Array = a[1:]
m = Matrix([[1, 2], [3, 0]], bits=2)
row: Array = m[0]
cell: int = m[0, 0]

x = xp.asarray(a)
scalar: xp.Array = x[0]  # A zero-dimensional array, not a Python int.
total: xp.Array = xp.sum(x)
bits: int = x.storage_bits
with xp.strict():
    x[0] = 1
```

Typing distinguishes native scalar access, native slices/rows, rectangular and
ragged shapes, and Array API scalar arrays. Arithmetic and reductions return
Array API arrays; multi-result operations declare tuples or named tuples with
array fields. The standardized linalg/FFT entry points are also declared.
Native NumPy arithmetic returns ndarrays. Native layout and bit-width arguments
use literals; a dynamic integer bit width may need validation and a cast in
strictly checked caller code.

Logical dtype and storage width remain separate. Arrays are not generic over
dtype, shape, or storage width in this version. NumPy outputs therefore retain
an unspecified dtype in their annotation, while native `.dtype` is uint8.
Value ranges, broadcasting compatibility, dimension validity, and overflow are
still checked at runtime. A static `Array[Literal[3]]` would be misleading for
shared storage that can widen through another view. Broad conversion boundaries
such as `asarray(obj)` accept `object`; they do not statically validate every
possible input object. Private implementation APIs and extra NumPy-specific
extension functions are outside this public typing contract.

Run `python scripts/check-types.py`. It builds a wheel, checks the type files are
included, extracts it outside the checkout, and runs strict mypy on both the
stubs and a consumer fixture. Return types use `assert_type`; deliberately invalid
calls use error-specific ignores with unused-ignore checking enabled. A lost
error or a return type silently becoming Any fails the relevant fixture assertion.
Runtime tests check namespace coverage and structured return fields. The same
checks run in the Linux/macOS, Python 3.12/3.14 CI matrix. Other type checkers have
not yet been tested.
