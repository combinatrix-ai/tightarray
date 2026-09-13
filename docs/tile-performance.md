# Narrow tile accumulators and row dispatch

Baseline: e3e0605. Apple M1 Pro, CPython 3.13.15, NumPy 2.5.3.
The baseline was measured in two batches (bits 1/3/5/8 and 2/4/6/7).
Both revisions use the same deterministic random inputs, approximately 65,536
values per matrix, ten widths (16–1,024), and offsets 0, 1, and 7.
Each timing is the median of seven calibrated samples. Construction is excluded;
Array API timings include conversion of the reduction output to NumPy.
Every output is checked against NumPy uint64 sum. Thread counts are set to one.
These are warm-cache microbenchmarks, not a universal speed guarantee.

Column sums accumulate into uint16 when rows × maximum value fits; otherwise
uint32 batches are flushed into uint64 before overflow. A column tile uses at
most 1 KiB decoded bytes plus 4 KiB accumulators on the stack, in addition to
view descriptors. No full-size input expansion is introduced. Row dispatch uses
bit-width/layout limits and preserves word-folding paths for aligned rows where
the tile experiment regressed. The limits are conservative M1 measurements,
not an exhaustive search of every shape or other CPU.

## Aggregate results

| Reduction | Median old/new ratio | Cases slower by more than 10% | Cases |
|---|---:|---:|---:|
| Column sum | 1.24× | 0 | 480 |
| Row sum | 1.01× | 0 | 480 |

## Example: packed 5-bit, offset zero

| Columns | Axis | Before µs | After µs | NumPy µs |
|---:|---|---:|---:|---:|
| 33 | 0 | 44.89 | 40.03 | 45.73 |
| 33 | 1 | 39.13 | 16.48 | 21.59 |
| 64 | 0 | 28.30 | 21.87 | 40.06 |
| 64 | 1 | 24.29 | 15.55 | 18.49 |
| 128 | 0 | 23.20 | 18.97 | 38.24 |
| 128 | 1 | 17.88 | 15.06 | 15.10 |
| 256 | 0 | 20.46 | 16.64 | 35.32 |
| 256 | 1 | 14.52 | 14.67 | 12.96 |

## Remaining regressions (>10% slower)

| Bits | Layout | Width | Offset | Axis | Old/new ratio |
|---:|---|---:|---:|---:|---:|
| — | None observed in this run | — | — | — | — |

Earlier candidate runs showed small-width losses, which did not exceed 10%
in the final run. This variation needs repeated-run study. Timing variation and
separate baseline batches also affect small differences. Large-stride and ND
traversal were not changed in this experiment. Heap tracing in the raw results
does not include C stack buffers or represent total process memory.

Tests cover every bit width/layout, 16-to-32-bit accumulator boundaries,
column tile tails, row dispatch boundaries, negative/stepped row strides, and
an actual uint32 batch overflow boundary using a zero-stride repeated-row view.

Reproduce with `benchmarks/tile_experiment.py --label LABEL --output FILE`
against each installed revision, then run this report script. Raw results:
[before](results/tiles-before.json), [after](results/tiles-after.json).
