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
scalar: xp.Array[xp.uint8] = x[0]  # A zero-dimensional array, not a Python int.
total: xp.Array[xp.uint64] = xp.sum(x, dtype=xp.uint64)
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

## Logical dtype parameters

`xp.Array[DType]` is invariant and tracks the logical NumPy scalar type. The
parameter does not describe the packed bit width. It can be used in evaluated
annotations and with `typing.get_type_hints`; no specialized array subclass or
new data allocation is created by the annotation.

```python
x = xp.asarray([0, 1, 7], dtype=xp.uint8)  # Array[uint8], 3-bit storage
view = xp.reshape(x, (1, 3)).T           # Array[uint8]
mask = x > 1                            # Array[bool]
floats = xp.astype(x, xp.float32)        # Array[float32]
x[0] = 31                               # warning; still Array[uint8], now 5-bit
```

Explicit `dtype=` scalar classes and typed `np.dtype` objects drive inference
for construction, casts, and sum/prod/cumulative reductions. Existing typed
Array API/NumPy arrays preserve dtype through `asarray` with no cast; native
Array inputs imply uint8. Basic indexing, iteration, reshape, permutations and
other dtype-preserving views keep the parameter. Comparisons and predicates
return bool arrays. Like-constructors preserve input dtype unless overridden.

Use `xp.uint8`, `xp.float32`, etc. for typed dtype arguments. General dtype
spellings such as strings retain `Array[Any]` when the checker cannot determine
the dtype; `np.dtype` inference may itself resolve literal strings. Python
built-in dtype classes and structured dtype specifications remain accepted by
some runtime conversions but are outside the precise typed constructor/cast
signatures in this phase. Keeping these boundaries explicit prevents a broad
Any-returning overload from hiding known dtype mismatches.

Plain `xp.Array` defaults to `xp.Array[Any]`. Arithmetic promotion, implicit
reduction dtypes, most linalg/FFT dtypes, and untyped input conversion currently
retain this unknown parameter. The array container itself remains typed. Explicit
dtype parameters are invariant: `Array[uint8]` cannot be passed where
`Array[uint16]` or `Array[np.generic]` is required. Use `Array[Any]` for a consumer
that deliberately accepts arbitrary dtypes, and `astype` for conversion.

Shape and storage width remain runtime metadata. Value ranges, broadcasting
compatibility, dimension validity, and overflow are still checked at runtime.
Annotations do not enforce runtime dtype or alter casting/promotion behavior.
Broad conversion boundaries such as `asarray(obj)` accept `object`; they do not
statically validate every possible input object. Private APIs and extra
NumPy-specific extension functions are outside this public typing contract.

Run `python scripts/check-types.py`. It builds a wheel, checks the type files are
included, extracts it outside the checkout, and runs strict mypy on both the
stubs and a consumer fixture. Return types use `assert_type`; deliberately invalid
calls use error-specific ignores with unused-ignore checking enabled. A lost
error or a return type silently becoming Any fails the relevant fixture assertion.
Runtime tests check namespace coverage and structured return fields. The same
checks run in the Linux/macOS, Python 3.12/3.14 CI matrix. Other type checkers have
not yet been tested.
