# Static typing

Public `.pyi` stubs and `py.typed` ship in the wheel, following the
[Python typing distribution specification](https://typing.python.org/en/latest/spec/distributing.html).
Install `.[typecheck]` and run `python scripts/check-types.py`.

```python
from tightarray import Array, Matrix
from tightarray import array_api as xp

a = Array([1, 2, 3], bits=2)
value: int = a[0]
part: Array = a[1:]
m = Matrix([[1, 2], [3, 0]], bits=2)
row: Array = m[0]
cell: int = m[0, 0]

x = xp.asarray(a)                       # Array[uint8]
scalar: xp.Array[xp.uint8] = x[0]        # Zero-dimensional array.
view = xp.reshape(x, (1, 3)).T          # Array[uint8]
mask = x > 1                           # Array[bool]
floats = xp.astype(x, xp.float32)       # Array[float32]
total = xp.sum(x)                       # Array[uint64]
x[0] = 31                              # Warning; dtype stays uint8.
```

## Known and unknown logical dtypes

`xp.Array[DType]` is invariant and tracks the logical scalar type, independently
of the packed bit width and shape. The parameter supports evaluated annotations
and `typing.get_type_hints`; it does not create a specialized runtime array or
validate values at runtime.

Explicit `dtype=` NumPy scalar classes and typed `np.dtype` objects drive
inference for construction, casts and reductions. Existing typed Array API or
NumPy arrays preserve dtype through `asarray` without a cast; native Array inputs
imply uint8. Basic indexing, iteration and dtype-preserving views retain it.
Comparisons/predicates return bool; index/count outputs use platform integer
arrays. Default sum/prod/cumulative reductions use uint64 for unsigned input,
int64 for signed/bool input, and retain floating/complex input dtype.

When dtype is not statically known, results use `Array[Scalar]`. `Scalar` is the
explicit union of the 13 supported bool, integer, floating and complex scalar
types. It is not a dynamic escape hatch: an unknown result cannot be passed as
`Array[uint8]` or assigned to a variable of that type without an explicit cast or
conversion. Plain `xp.Array` defaults to this bounded unknown parameter.

```python
unknown = xp.asarray([1, 2])       # Array[Scalar]; list inference is deferred.
def needs_bytes(x: xp.Array[xp.uint8]) -> None:
    pass
needs_bytes(unknown)               # Type error.
needs_bytes(xp.astype(unknown, xp.uint8))  # OK.
```

Arithmetic promotion and most linalg/FFT result dtypes are still conservative
bounded unions, not exact promotion tables. Multi-result containers and their
fields remain typed. Native NumPy numeric operators similarly return a bounded
numerical ndarray; conversion without a cast preserves uint8.

An invariant `Array[uint8]` is not an `Array[Scalar]`. Functions that preserve an
arbitrary caller dtype should use a type variable:

```python
from typing import TypeVar
T = TypeVar('T', bound=xp.Scalar)
def row(x: xp.Array[T]) -> xp.Array[T]:
    return x[0]
```

Public operations accept any supported input dtype through read-only metadata
protocols where necessary. `__array_namespace__()` has a typed protocol with
standard functions and extensions, rather than an unconstrained module result.
That protocol is generated from the public signatures; CI rejects stale copies.

Use `xp.uint8`, `xp.float32`, etc. for precise dtype arguments. Strings remain
bounded unknowns unless NumPy's dtype typing resolves them. Built-in Python
dtype classes, structured/object dtype conversions, private APIs and additional
NumPy-specific extension functions are outside these numerical type signatures.
Runtime casting and promotion behavior is unchanged. Shape compatibility,
value ranges and overflow remain runtime checks. `asarray(obj)` accepts `object`
and does not statically validate all possible conversion inputs.

## Verification

`tightarray.compressed.CompressedArray` has a fixed logical uint8 range; scalar
indexing returns `int`, slices and `read` return `bytes`, and `storage_info` returns
the frozen `StorageInfo` dataclass. Physical widths and palettes are runtime
storage choices, not type parameters. The compressed module ships its own stubs
and a consumer fixture checked with `--disallow-any-expr`.


The checker builds a wheel, verifies that its type files are included, extracts
it outside the checkout, and runs strict mypy on stubs and consumer fixtures.
Return types are asserted; invalid calls use error-specific ignores and
unused-ignore checking. It also rejects explicit `Any` in distributed stubs and
runs a consumer fixture with `--disallow-any-expr`, including array results,
dtype metadata, NumPy exports, linalg/FFT, and namespace dispatch.

Runtime tests check namespace coverage, named results, evaluated annotations,
all 13 dtypes and default reduction promotion. Checks run in Linux/macOS,
Python 3.12/3.14 CI. This guards the public contract; it is not a claim that all
internal Python implementation functions or all third-party NumPy APIs are
fully annotated. Other type checkers have not yet been tested.
