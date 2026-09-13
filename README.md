# tightarray

Compact small-integer arrays for CPython, initially optimized for Apple M1 Macs.

An experimental C extension for unsigned 1–8 bit values. Supports 1D arrays,
rectangular matrices, and ragged rows without retaining a Python object per
value or row. The core has no DNA, amino-acid, or other domain-specific encoding.

## Install and test

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
python -m pytest -q
```

Requires CPython 3.10+ and a C compiler. The tested targets are ARM64 macOS with
CPython 3.12 and 3.14. Builds on ARM64 macOS use `-O3 -mcpu=apple-m1`.
Other little-endian targets have portable C kernels but are not yet validated.
Free-threaded execution and subinterpreters are not supported; operations retain
the GIL. ARM64 kernels use NEON for packing and shifted copying, alongside
constant-width word operations and libc copying/comparison. Defining
`TIGHTARRAY_NO_NEON` selects the portable C packing/copy fallback.

## Use

```python
from tightarray import Array, Matrix, RaggedArray

values = Array([0, 1, 3, 2], bits=2, layout="packed")
assert values[-1] == 2
values[1] = 3
assert values.count(3) == 2
assert values.find([3, 2]) == 2
assert values.gather([3, 0]).tolist() == [2, 0]

part = values[1:3]       # shared view, no data copy
part[0] = 0             # updates values[1]
independent = part.copy()
assert values.tobytes() == bytes([0, 0, 3, 2])  # unpacked bytes

matrix = Matrix([[0, 1], [2, 3]], bits=2)
matrix[1, 0] = 1        # direct C indexing; no intermediate row object
matrix[0][1] = 2        # row view shares the buffer
assert matrix.shape == (2, 2)

ragged = RaggedArray([[], [1, 2], [3]], bits=2)
assert ragged[1, -1] == 2
assert ragged.shape == (3, None)

# Flat constructors avoid materializing Python rows.
matrix = Matrix.from_flat(bytes([0, 1, 2, 3]), (2, 2), bits=2)
ragged = RaggedArray.from_flat(bytes([1, 2, 3]), [0, 0, 2, 3], bits=2)
```

All structures accept `layout="packed"` or `layout="word-aligned"`.
Array values must implement integer indexing and fit the selected width; invalid
values raise instead of truncating. Arrays have fixed size. Negative indices are
supported. Scalar assignment is supported; resizing and slice assignment are not.

Contiguous slices share data. Slices with a non-unit step copy. Ragged contiguous
row slices share data but allocate normalized row offsets. Views keep their root
allocation alive. `copy()` always returns independently mutable data. Array
and Matrix comparisons return elementwise NumPy boolean arrays with broadcasting.
Use `.equals()` for native whole-container equality, including across bit widths
and layouts. Ragged equality remains a whole-container comparison.

`find()` returns the first subsequence position or -1; an empty needle returns 0.
`count()` counts values across all rows for matrix/ragged containers. Out-of-range
integers have count zero. `gather` accepts native contiguous signed-index buffers
(such as NumPy `intp`) without constructing Python integers, as well as iterables. Row-wise find/count can use a row view. The raw packed
buffer is intentionally not exposed as a misleading NumPy uint8 array;
`tobytes()` and `tolist()` explicitly unpack values.

## NumPy integration

Install the optional `numpy` extra for conversions, elementwise operators, and
NumPy dispatch. `np.asarray` unpacks to a writable uint8 ndarray; `np.copy` and
selected `np.take` calls retain packed storage. General arithmetic returns NumPy
results. See [the supported subset and explicit boundaries](docs/numpy.md).

For the standard Python Array API, install `.[array-api]` and use
`tightarray.array_api`. It provides packed uint8/bool ND arrays and NumPy-backed
other dtypes. See [conformance results and limitations](docs/array-api.md).

## Representation

| Structure | Retained representation |
| --- | --- |
| Array | Native buffer, element count, bit width, layout |
| Matrix | One Array plus native row and column counts |
| RaggedArray | One Array plus a native offsets buffer |
| Array API ND | Shared packed root plus shape/strides; NumPy for other dtypes |

- **Packed**: dense fixed-width bit stream; elements can cross 64-bit boundaries.
- **Word-aligned**: whole elements within each 64-bit word, with unused tail bits.
  A 5-bit word holds 12 elements and leaves 4 bits unused.

Bits 1, 2, 4, 8 divide a byte. Bits 3, 5, 6, 7 have specialized boundary handling.
Allocation is rounded to 64-bit words, with a minimum 8-byte data allocation.
Buffers are not serialized file formats; bit order and persisted-format stability
are not promised in this development version.

`nbytes` reports owned logical buffer allocation, excluding object headers; a
1D view owns zero data bytes. `sys.getsizeof(Array)` includes its owned buffer but
not the root retained by a view (`base`). Matrix/ragged `__sizeof__` includes their
native children and any root array they keep alive. Benchmark accounting handles
these distinctions and counts shared Python objects once.

## Benchmarks and safety checks

```sh
python benchmarks/run.py --output benchmarks/results/local.json
python benchmarks/run.py --output benchmarks/results/large.json --sizes 1048576
PYTHON="$VIRTUAL_ENV/bin/python" sh scripts/check-sanitizers.sh
```

Each method is compared with standard Python and NumPy for retained memory,
additional traced peak memory, and execution time. Sequence cases also include
bytes/str. Both tightarray layouts are reported separately. Identical values are
verified before timing. View creation and copying are separate operations.

See [measurement plan](docs/benchmarks.md) and [measured results](docs/performance.md).
Speedups are method- and workload-specific; this is not a claim that packing makes
every operation faster. Python scalar loops, construction from object-heavy
inputs, long-needle search, and nonaligned copies remain optimization targets.

## Status

Implemented: core arrays, matrices, ragged rows, shared views, mutation, copy,
gather, conversion, comparison, count, and subsequence search. Boundary tests,
randomized reference checks, and ASan/UBSan checks accompany optimized kernels.

Deferred: native C N-dimensional kernels, resizing, serialization/mmap,
Zero-copy NumPy dtype integration, parallel mutation, and wider-platform tuning.
The name is provisional; package-name availability has not been checked.
Licensing and public publication remain pending decisions.
