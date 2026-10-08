# tightarray

Compact small-integer arrays for CPython, initially optimized for Apple M1 Macs.

An experimental C extension for unsigned 1–8 bit values. Supports 1D arrays,
rectangular matrices, and ragged rows without retaining a Python object per
value or row. The core has no DNA, amino-acid, or other domain-specific encoding.

## What it is for

The main benefit is **memory footprint**: fitting more small-integer state into
the same RAM. It is usually not a speedup by itself. Measured results:

| Workload | Memory result | Cost | Details |
| --- | --- | --- | --- |
| Multi-state cellular automaton under a 512 MiB process RSS budget | 3-bit: **2.61× more cells** than uint8 (462M vs 177M); 5-bit: 1.51× | Per-cell update time about 1.1× uint8 at those sizes | [capacity grid](docs/capacity-grid.md) |
| Diploid genotypes with missing calls (scikit-allel queries) | **Half the payload** of scikit-allel's own packed format (4.0 vs 8.0 MiB) | Similar query time | [genotypes](docs/explore-genotypes.md) |
| Sokoban search visited-state keys | **25% less** retained key memory than uint8 | 12% slower | [Sokoban](docs/real-sokoban-search.md) |
| DeepRC repertoire sequences | **37.5% smaller** sequence payload | Extraction slightly slower | [bio pilots](benchmarks/bio/README.md) |

General-purpose compression wins when values repeat spatially or are highly
skewed: Blosc2 stores the genotype data in less space, and ZSTD beats packing on
MiniGrid replay history and segmentation masks
([storage exploration](docs/storage-exploration.md),
[non-bio experiments](docs/nonbio-experiments.md)). The capacity figures are the
largest completed sizes from a 1024-step search, not exact maxima.

## Immune-repertoire software

tightarray is also used to improve machine-learning software for
immune-repertoire analysis, starting with
[MotifBoost](https://github.com/hmirin/MotifBoost)
([paper](https://doi.org/10.3389/fimmu.2022.797640)). The optional
[`tightarray-immune`](packages/tightarray-immune/README.md) package connects
the core arrays to existing tools without modifying installed applications.
Each connector is tested against a pinned upstream commit:

| Tool | Pinned upstream | Connector | Time | Memory |
| --- | --- | --- | --- | --- |
| MotifBoost | [`0fd515b`](https://github.com/hmirin/MotifBoost/tree/0fd515b787cd0834c02becefc772bc6059247d5a) | Opt-in feature backend for actual `fit` / `predict_proba` | Load + fit + predict median 194.2 → 136.2 ms ([details](docs/bio-motifboost-pipeline.md)) | Peak RSS unchanged (350.8 vs 350.3 MiB); upstream strings and dense features are still retained |
| immuneML | [`24d74abb`](https://github.com/uio-bmi/immuneML/tree/24d74abb2d30b081f9d6359a688a3e827c983e44) | Continuous k-mer encoder dispatch ([AGPL-3.0 patch](benchmarks/bio/patches/README.md)) | Encoding + classifier pipeline 41.36 → 14.26 s ([details](docs/bio-immuneml-pipeline.md)) | Same feature matrix (333,372 bytes) |
| DeepRC | [`108d08d`](https://github.com/ml-jku/DeepRC/tree/108d08d8cf2d2d69eb3f6caef1aa04d624dec871) | Padded batch extraction | Slightly slower | Sequence payload 53,314 → 33,328 bytes |
| Scirpy | [`eb04a91`](https://github.com/scverse/scirpy/tree/eb04a91cc2f07bfc38c84f4d3ce6778c6fc2cb27) | Symmetric Hamming distance with cutoff (CSR) | Faster mainly by avoiding per-call JIT setup | Lower RSS, mostly from less Numba compilation |

All connectors reproduce upstream outputs exactly (Scirpy against its reference
matrix). BioNumPy and CompAIRR were also compared; neither showed a gain.
Measurements use small bundled example datasets on one ARM64 Mac, where imports
and JIT dominate process memory, so they do not yet show a whole-process RAM
reduction. Most of the speedup comes from removing string conversions, not from
bit packing. No biological or clinical performance is claimed. Larger
repertoires under a fixed memory budget are the next measurement. See the
[bio application pilots](benchmarks/bio/README.md) for methods and limits.

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
assert values.sum() == 8
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

## Optional compressed storage

For optional per-chunk uniform/palette compression, LZ4/ZSTD, and a bounded packed
cache, see the experimental [`CompressedArray`](docs/compressed-storage.md).
It keeps a fixed logical uint8 range while choosing physical widths per chunk.
It is intended for read-mostly storage; the document compares retained metadata,
cache budgets, and read/write costs against NumPy and a cached Blosc2 baseline.

## Static typing


Public type stubs cover native containers and the Array API namespace, including
standard linalg/FFT operations. `array_api.Array[DType]` tracks logical dtype
through explicit construction, views, comparisons, and casts; packed storage
width remains runtime metadata. Unknown dtypes use a bounded `Scalar` union;
the public stubs contain no `Any`. Install `.[typecheck]` and run
`python scripts/check-types.py` to validate the wheel and consumer examples.
See [typing scope and examples](docs/typing.md).

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

See [measurement plan](docs/benchmarks.md), [measured results](docs/performance.md),
[competitor comparisons](docs/competitor-performance.md), and the latest
[shared-kernel experiment](docs/core-performance.md) and
[C view experiment](docs/cview-performance.md), followed by
[strided and axis reductions](docs/axis-performance.md), and
[narrow tile accumulators](docs/tile-performance.md).
The [bio application pilots](benchmarks/bio/README.md) cover MotifBoost, immuneML,
BioNumPy, Scirpy, DeepRC and CompAIRR, separating numeric-pipeline gains from
packing-specific effects.
The separately installable [immune adapters](packages/tightarray-immune/README.md)
provide explicit feature, padding and distance interfaces for four of those tools.
Speedups are method- and workload-specific; this is not a claim that packing makes
every operation faster. Python scalar loops, construction from object-heavy
inputs, long-needle search, and nonaligned copies remain optimization targets.

Optional [Numba packed access and lattice simulation](docs/numba.md) provides
zero-copy descriptors, checked fixed-width writes, and a three-backend benchmark.

## Status

Implemented: core arrays, matrices, ragged rows, shared views, mutation, copy,
gather, conversion, comparison, count, native sum, and subsequence search.
Array API conversion, basic assignment and whole-view sum share validated C kernels;
see [the architecture and remaining boundaries](docs/shared-kernels.md). Boundary tests,
randomized reference checks, and ASan/UBSan checks accompany optimized kernels.

Deferred: full native C N-dimensional execution, resizing, serialization/mmap,
Zero-copy NumPy dtype integration, parallel mutation, and wider-platform tuning.
The name is provisional and conflicts with existing libraries; a replacement is pending.
Licensed under [Apache-2.0](LICENSE), except the immuneML patch (AGPL-3.0).
