# C Array API views and bounded-memory widening

For the subsequent stride and axis work, see [the reduction experiment](axis-performance.md).

Baseline: `758f6bf`. Apple M1 Pro, CPython 3.13.15, NumPy 2.5.3.
Control implementations and benchmark inputs are unchanged. Times are microseconds.

## Five-bit arrays, 65,536 elements

| Operation | Previous Array API µs | C view µs | NumPy µs |
| --- | ---: | ---: | ---: |
| get-scalar | 0.781 | 0.085 | 0.064 |
| set-restore | 3.796 | 0.165 | 0.154 |
| assign-32 | 4.137 | 3.758 | 0.292 |
| sum | 10.032 | 10.512 | 13.095 |
| strided-sum | 19.999 | 21.098 | 10.302 |

The scalar fast path accepts Python integer indices (including full ND index tuples)
and Python integer assignment values. NumPy scalar indices/values, slices, masks, and
other casts still use the Python/NumPy fallback. Set/restore includes one read and two writes.

## Matrix scalar operations, 256 × 256

| Operation | Previous Array API µs | C view µs | NumPy µs |
| --- | ---: | ---: | ---: |
| matrix-get | 2.521 | 0.097 | 0.071 |
| matrix-set-restore | 9.118 | 0.189 | 0.163 |

## Width growth, 1,048,576 elements

| Layout | Width | Before µs | After µs | Before traced peak KiB | After traced peak KiB |
| --- | --- | ---: | ---: | ---: | ---: |
| packed | 1 → 2 | 213.25 | 237.54 | 1280.7 | 256.1 |
| packed | 3 → 5 | 361.25 | 310.38 | 1664.7 | 640.1 |
| packed | 5 → 8 | 218.71 | 184.08 | 2048.7 | 1024.1 |
| word-aligned | 1 → 2 | 181.62 | 168.67 | 1280.7 | 256.1 |
| word-aligned | 3 → 5 | 273.75 | 290.04 | 1707.3 | 682.8 |
| word-aligned | 5 → 8 | 185.75 | 153.12 | 2048.7 | 1024.1 |

Width timing excludes input construction and reports nine independent samples, each starting
with a fresh array. The entire result is checked against NumPy. These single-operation
measurements have more timer/cache noise than the calibrated scalar measurements.
Traced peak includes the required new packed allocation but excludes preexisting storage and C stack memory.
Repacking uses at most a 1 KiB stack buffer; expansion to 8 bits writes directly to the new allocation.
Growth remains O(n), and individual layout/width combinations may trade some speed for bounded temporary memory.

## Implementation boundary

- A GC-aware C base type owns Array API metadata and supplies indexing, assignment, integer/float conversion slots.
- Scalar views share a C storage cell. Its replacement allocation is published only after repacking completes.
- Shape and stride tuples remain Python objects. ND descriptors are still parsed for bulk kernels; this is not a complete native ND executor.
- NumPy-backed dtypes and general operations preserve their fallback behavior.
- Strided/axis kernels remain the next performance target. The benchmark does not establish wins for all indexing/casting forms.

## Reproduce

```sh
python benchmarks/core_experiment.py --label current --output scalar.json
python benchmarks/view_experiment.py --label current --output width-and-matrix.json
python benchmarks/report_view_experiment.py
```

Use the same script with baseline/current wheels, set OMP_NUM_THREADS, OPENBLAS_NUM_THREADS
and VECLIB_MAXIMUM_THREADS to 1, and run timings without concurrent jobs.
Raw measurements are in `docs/results/m1-cview-*.json`.
