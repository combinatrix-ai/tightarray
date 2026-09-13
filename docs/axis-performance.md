# Strided and axis reduction experiment

Later measurements: [narrow tile accumulators and row dispatch](tile-performance.md).

Baseline: `bbd572d`. Apple M1 Pro, CPython 3.13.15, NumPy 2.5.3, one thread.
All inputs contain 65,536 random unsigned values. Views and input construction are
excluded from timing. Results are checked against NumPy before seven calibrated
samples. Array API timings include conversion of the result to a NumPy array.

## Five-bit results

| Operation | Previous packed µs | Packed µs | Aligned µs | NumPy µs |
| --- | ---: | ---: | ---: | ---: |
| stride-2 | 26.28 | 6.62 | 4.09 | 14.23 |
| stride-3 | 18.77 | 6.25 | 5.10 | 9.81 |
| stride-4 | 13.91 | 4.14 | 3.50 | 7.65 |
| stride-17 | 4.70 | 4.73 | 4.28 | 2.40 |
| matrix-256x256-axis-0 | 49.23 | 20.88 | 22.58 | 36.75 |
| matrix-256x256-axis-1 | 26.76 | 14.52 | 9.25 | 13.16 |
| matrix-2048x32-axis-1 | 35.42 | 15.43 | 15.02 | 21.85 |
| nd-axes-0-2 | 28.87 | 18.91 | 13.04 | 15.25 |

Axis 0 sums columns; axis 1 sums rows. The ND case has shape (16, 32, 128).

## Stride 3 across bit widths

| Bits | Packed µs | Aligned µs | NumPy µs |
| ---: | ---: | ---: | ---: |
| 1 | 2.88 | 2.73 | 9.81 |
| 2 | 6.51 | 6.21 | 9.76 |
| 3 | 6.06 | 4.08 | 9.75 |
| 4 | 6.24 | 6.17 | 9.77 |
| 5 | 6.25 | 5.10 | 9.81 |
| 6 | 6.15 | 4.85 | 9.58 |
| 7 | 6.32 | 4.45 | 9.98 |
| 8 | 4.64 | 4.65 | 9.70 |

## Allocation during reduction

| Five-bit packed operation | Before traced peak B | After traced peak B |
| --- | ---: | ---: |
| stride-3 | 609 | 689 |
| matrix-256x256-axis-0 | 135289 | 3093 |
| matrix-256x256-axis-1 | 135289 | 3093 |
| matrix-2048x32-axis-1 | 149625 | 17525 |
| nd-axes-0-2 | 100769 | 1253 |

Tracemalloc is not RSS: C stack allocations are excluded. Axis kernels retain only
the required result plus rank-bounded descriptors and at most a 1 KiB decode buffer.
The input is never fully expanded on these native reduction paths.

## Native paths and limits

- Packed bool/uint8 sums support one axis, tuples of axes, negative axes, empty axes, empty input and keepdims. Default accumulation and explicit uint64 use C; other requested dtypes still use NumPy.
- Strides 2/3/4 use fixed masks over byte-aligned packed groups or physical aligned words when the starting offset permits. Other offsets use a generic masked or scalar reader.
- Negative strides are traversed in reverse order and zero strides use multiplication. Integer addition is exact within the uint64 accumulator, modulo overflow.
- Generic masked groups require at least four selected lanes; applying them to stride 17 on 2/3-bit values was slower and was rejected.
- Column reductions decode contiguous column tiles, then accumulate into uint64 outputs. Many short contiguous rows are decoded together. Other ND layouts traverse reduction runs.
- Large strides, arbitrary starting offsets, some row shapes, and general multi-axis layouts still have room for improvement. These results do not claim a win for every shape or dtype.

## Reproduce

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 python benchmarks/axis_experiment.py --label current --output axis.json
python benchmarks/report_axis_experiment.py
```

Run the same harness against baseline and current wheels in the same environment.
Raw results: [before](results/m1-axis-before.json), [after](results/m1-axis-after.json).
