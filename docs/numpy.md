# NumPy interoperability

Install `tightarray[numpy]`. The native core and its `.equals()` method work without
NumPy; NumPy conversions, operators, and dispatch import it lazily.
This is an initial supported subset, not a drop-in ndarray replacement.

```python
import numpy as np
from tightarray import Array, Matrix

a = Array([0, 1, 2, 3], bits=2)
b = np.asarray(a)                 # independent, writable uint8 ndarray
assert a.shape == (4,) and a.ndim == 1 and a.size == 4
assert a.dtype == np.dtype('uint8')
assert (a == 2).tolist() == [False, False, True, False]
assert a.equals(a.copy())         # native whole-array equality
assert np.array_equal(a, b)
assert np.count_nonzero(a) == 3
assert isinstance(np.copy(a), Array)
assert isinstance(np.take(a, np.array([3, 0], dtype=np.intp)), Array)
assert (a + 1).tolist() == [1, 2, 3, 4]

m = Matrix([[0, 1], [2, 3]], bits=2)
assert (m + np.array([1, 2], dtype=np.uint8)).tolist() == [[1, 3], [3, 5]]
```

| Operation | Result and storage |
| --- | --- |
| `np.asarray`, `np.array` | Unpack to an independent, writable ndarray; optional dtype conversion |
| `np.array_equal`, `.equals()` | Whole-value equality; native comparison for two compatible tightarray containers |
| `==`, `!=`, `<`, `<=`, `>`, `>=` | Elementwise NumPy boolean ndarray, with broadcasting |
| `np.copy` | Independent packed Array/Matrix; Matrix `order='F'` returns a Fortran-order ndarray |
| `np.take` | Packed Array for a 1D native-intp index array with normal bounds checking and no `out`; other cases return an ndarray |
| `np.count_nonzero` | Native count for `axis=None`; other reductions unpack first |
| Ufuncs such as `np.add`, `.reduce`, `.accumulate` | Unpack, then delegate computation and promotion to NumPy; return NumPy results |
| `+`, `-`, `*`, `/`, `//`, `%`, `&`, `\|`, `^`, `<<`, `>>` | Corresponding NumPy ufunc semantics and result dtype |
| `np.sum`, `prod`, `mean`, `min`, `max`, `all`, `any` | NumPy reductions after unpacking |
| `np.concatenate`, `stack`, `reshape`, `transpose` | NumPy arrays after unpacking |

Arithmetic retains NumPy's uint8 promotion and overflow behavior; the storage
width does not silently mask arithmetic results back to 1–8 bits. Packing a
result requires explicitly constructing an Array with a chosen width and range
validation. Array/Matrix truth testing requires exactly one element.

## Explicit boundaries

- Logical `dtype` is uint8 even for 1-bit values. `.bits` describes the storage
  width. Comparison results use NumPy's boolean dtype.
- No zero-copy NumPy export is implemented, including for 8-bit arrays.
  `copy=False` raises instead of violating that contract.
- Packed `out=` and mutation through `ufunc.at` are rejected. An ordinary ndarray
  `out=` is supported. Mutating an unpacked temporary never substitutes for
  mutating the packed source.
- General bit strides are not implemented: stepped basic slices still copy.
  Fancy/boolean `a[indices]`, Matrix column slicing, advanced assignment, and
  arbitrary-dimensional packed views remain future work. Use `np.take` for
  supported indexed copies.
- `.nbytes` retains its native meaning: owned buffer bytes, zero on an Array view.
  It is not NumPy's logical element-byte count.
- Unregistered NumPy functions return `NotImplemented` through the protocol and
  fail explicitly. Convert with `np.asarray(a)` to use the full ndarray API.
- RaggedArray remains a separate container with whole-container comparison;
  it does not opt into rectangular NumPy dispatch.
- Comparison operators changed from scalar/lexicographic comparison to
  elementwise comparison. Use `.equals()` for native whole-container equality.

See [measured NumPy API time and memory](numpy-performance.md).

Native method timing and NumPy entry-point timing are separate measurements:
`benchmarks/run.py` measures `.equals()` and `.gather()`, while
`benchmarks/run_numpy.py` includes NumPy dispatch/unpacking costs. The latter can
be slower than operating on an existing ndarray, even when the native packed
kernel is faster. Conversion allocates roughly one byte per element, temporarily
losing the packed memory advantage.

The implementation follows NumPy's official [custom container dispatch](https://numpy.org/doc/stable/user/basics.dispatch.html)
and [special method contracts](https://numpy.org/doc/stable/reference/arrays.classes.html).
