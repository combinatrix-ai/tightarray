# Capacity under a 512 MiB process RSS budget

`examples/capacity_grid.py` stores two planes as lists of independent rows.
Packed rows use tightarray; the control uses uint8 NumPy rows. Only three
neighbor rows and one output row are dense scratch. The same Numba row kernel
sums the periodic 3x3 Moore neighborhood modulo 8 or 32. Initial states are
generated one row at a time (seed 123). Final SHA256 and sum are streamed.
Neither initialization, stepping nor output creates a dense whole-grid array.

This is a capacity-oriented custom simulator, not the CellPyLib full-history
API. Its rule is checked against CellPyLib, plus direct NumPy reference tests
for tiny/rectangular grids and periodic edges. A 8192-square run compares
complete final hashes across dense/packed in separate processes. The larger
frontier runs do not materialize an independent full-size dense reference.

## Measurement contract

Each trial is a fresh process. Compilation is timed separately before
allocation. Peak RSS includes Python, NumPy, Numba/JIT, both state planes,
Python row objects, scratch buffers, initialization and streaming digest.
Both planes are physically touched during initialization. No mmap, disk spill,
whole-grid conversion or history retention is used.

The 512 MiB limit is a **cooperative observed RSS budget**, not an OS-enforced
memory limit or the machine's available RAM. Checkpoints inspect process
`ru_maxrss` every 128 rows and at phase ends. An over-budget run stops and is
recorded (small overshoot is possible). This does not test system OOM or prove
absence of OS compression/swap; process RSS is the explicit metric.

The search samples side lengths in increments of 1024, from documented
starting points. Results show the largest completed tested size and the next
rejected size, not an exact maximum or a proof of monotonic memory use.
Allocator size classes can change the slope. Each search trial runs 3 updates;
the largest successful dense/3bit/5bit cases are also run for 20 updates.
Timings are single-run observations, not a multi-host throughput benchmark.

```sh
python -m pip install -e '.[test,numba]' cellpylib==2.4.0
python -m pytest -q tests/test_capacity_grid.py
python -m benchmarks.capacity_grid
# Longer confirmation runs (JSON output per invocation):
python -m benchmarks.capacity_grid --worker 13312 8 dense --steps 20
python -m benchmarks.capacity_grid --worker 21504 8 packed --steps 20
python -m benchmarks.capacity_grid --worker 16384 32 packed --steps 20
```

Raw search results: `docs/results/capacity-grid.jsonl` (including environment).
Long confirmation runs: `docs/results/capacity-grid-long.jsonl`, same environment.

## Observed results

20-update confirmation runs on macOS arm64, Python 3.12.8, NumPy 2.5.3, Numba 0.67.0:

| Storage | Side length | Cells | Peak RSS | Median / update | Initialization | 20-update E2E |
|---|---:|---:|---:|---:|---:|---:|
| uint8 | 13,312 | 177,209,344 | 489.4 MiB | 0.395 s | 0.345 s | 8.62 s |
| 3bit | 21,504 | 462,422,016 | 457.7 MiB | 1.119 s | 0.872 s | 24.07 s |
| 5bit | 16,384 | 268,435,456 | 462.3 MiB | 0.658 s | 0.794 s | 14.95 s |

The next tested sides exceeded budget: uint8 14,336; 3bit 22,528; 5bit 17,408.
Compared with the largest tested uint8 grid, 3bit ran 2.61x as many cells and
5bit 1.51x. These are measured capacity gains for this state-dominated simulator,
not a promise for arbitrary applications. More agent attributes/history change
the total-memory ratio. The core library was unchanged.

Row streaming also amortizes bit extraction over neighborhood reuse: each row
is unpacked approximately once per generation and its three horizontal values
serve three output rows. This removes the previous per-neighbor packed reads.
Packing is still extra work, and the runs use different grid sizes; do not infer
a speedup from capacity measurements.
