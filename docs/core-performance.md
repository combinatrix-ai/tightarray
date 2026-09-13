# Common-kernel performance experiment

This records the shared-kernel baseline. See [the subsequent C view experiment](cview-performance.md)
for scalar dispatch and bounded-memory widening improvements.

Apple M1 Pro, CPython 3.13.15, NumPy 2.5.3, one thread. Baseline: `b793d1f`.
Times below are microseconds, medians of seven calibrated samples (at least 3 ms per sample, except the loop-count cap).
Inputs and results are checked against NumPy before timing. Python and NumPy controls use the same harness in both runs.

## Five-bit arrays, 65,536 values

| API | Operation | Before µs | After µs | Speedup |
| --- | --- | ---: | ---: | ---: |
| array-api | get-scalar | 12.638 | 0.782 | 16.2× |
| array-api | set-restore | 55299.041 | 3.780 | 14631.3× |
| array-api | assign-32 | 27577.125 | 4.179 | 6598.3× |
| array-api | small-view-to-numpy | 11.067 | 0.947 | 11.7× |
| array-api | sum | 26.205 | 10.003 | 2.6× |
| array-api | strided-sum | 25.014 | 20.965 | 1.2× |
| native-packed | sum | 340.958 | 8.839 | 38.6× |
| native-aligned | sum | 289.953 | 3.209 | 90.3× |

`set-restore` includes an integer read and two assignments. `assign-32` writes 32 strided elements.
No timed assignment increases storage width. The small conversion copies a preexisting 32-element view.
Native sum changes from Python `sum(a)` to the new `a.sum()` kernel; Array API retains the same `xp.sum(a)` call.

## Continuous sum across widths, 65,536 values

| Bits | NumPy uint8 µs | Native packed µs | Native aligned µs | Array API µs |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 12.529 | 0.218 | 0.218 | 1.402 |
| 2 | 12.618 | 1.538 | 1.539 | 2.709 |
| 3 | 12.548 | 6.297 | 2.339 | 7.467 |
| 4 | 12.517 | 2.413 | 2.414 | 3.598 |
| 5 | 12.543 | 8.839 | 3.209 | 10.003 |
| 6 | 12.553 | 10.657 | 3.845 | 12.598 |
| 7 | 12.517 | 8.908 | 4.286 | 10.415 |
| 8 | 12.525 | 2.001 | 2.003 | 3.187 |

## Scalar complexity and traced allocation

| Values | Read µs | Set/restore µs | Read peak B | Set peak B | Sum peak B |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 128 | 0.770 | 3.736 | 305 | 402 | 556 |
| 65,536 | 0.782 | 3.780 | 337 | 434 | 556 |
| 1,048,576 | 0.781 | 3.790 | 337 | 434 | 556 |

These are `tracemalloc` peaks per operation, not process RSS or total native memory. C stack storage is excluded:
the view descriptor uses approximately 1 KiB at its maximum supported rank. Reduction creates no decoded array.
Retained payload layouts are unchanged (5-bit packed uses approximately 5/8 of uint8 payload).

## Limits

- Array API scalar operations still create Python view/dtype objects and remain slower than NumPy scalars.
- The 6-bit Array API sum is approximately tied with NumPy in this run; small differences are not a robust win.
- Strided sum remains slower than NumPy, although the first experimental regression was removed.
- Widening storage is still O(n) and temporarily decodes the root; the constant-time mutation claim excludes widening.
- Other axis/dtype reductions and advanced indexing still use NumPy fallbacks.
- This warm-cache deterministic periodic workload is not a replacement for random/skewed competitor benchmarks.

## Reproduction

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 python benchmarks/core_experiment.py --label current --output current.json
python benchmarks/report_core_experiment.py
```

Run the same benchmark script with baseline and current wheels in the same environment.
Raw data: [before](results/m1-core-before.json), [after](results/m1-core-after.json).
Architecture and rejected alternatives: [shared kernels](shared-kernels.md).
