# Multi-state CA: finding the packing boundary

This pilot varies rule, alphabet, scale and history policy. It does not claim a
general-purpose CellPyLib backend. Code is in `examples/cellpylib_multistate.py`;
the reproducible runner is `benchmarks/cellpylib_multistate.py`.

## Workloads

- **Totalistic (9 reads/cell):** next state = sum of the Moore neighborhood,
  including the center, modulo state count. The reference calls the actual
  `cellpylib.totalistic_rule` with the equivalent base-k rule number.
- **Cyclic (up to 5 reads/cell):** a cell advances if one of its four cardinal
  neighbors has the next cyclic state. A custom callback runs in CellPyLib.
- **Transport (1 read/cell):** copy the western neighbor. A bandwidth-oriented
  control, not evidence of a useful simulator by itself.

All use periodic boundaries, synchronous updates, uint8 input/output, random
seed 123, and 3 updates. `simulate` counts updates; CellPyLib's `timesteps`
includes the initial frame, so its call uses 4. Widths are inferred from state
count, not observed random values. Packed writes have width/bounds checks;
dense Numba accesses use its default unchecked indexing, as in the Life pilot.

The measured backends are NumPy vectorized expressions, Numba uint8, Numba
packed, and Numba word-aligned. Full-history cases additionally measure the
unmodified upstream CellPyLib with memoization disabled/enabled. Recursive
memoization is not included in this sweep; no claim of beating every possible
upstream configuration is intended.

## Two different contracts

1. **Real CellPyLib comparison:** 64 x 64, 4/8/16/32 states, all 3 rules.
   All return every generation as a dense ndarray. Whole-history hashes must
   match; direct array equality is also checked in regression tests.
2. **Final-only scale study:** 256/1024/4096 square, 8/32 states, all 3 rules;
   additionally 8192 square for transport. Only the final dense frame is
   returned. This is a custom simulator experiment with upstream-validated
   rules, NOT a CellPyLib E2E speedup claim. All final frame hashes must match
   across NumPy, dense Numba and both packed layouts.

Each case/backend runs in a fresh child process. A separate 8 x 8 call warms
JIT; its cost is recorded. The three measured warm E2E calls include random
input creation, validation, storage allocation/encoding, all updates, and final
materialization. Imports/JIT warmup and validation hashes are outside timing.
Peak RSS includes all of those, imports, JIT and hashing across the process
lifetime. Buffer payload counts only the two state buffers and is not RSS.
The final-only API still transiently retains the initial dense input and
materializes the final output; it is not an entirely packed application.

This is a single-host exploratory sweep, with alternating backend order and
three samples. It does not establish hardware-independent bandwidth saturation
or an application-specific production benefit. Larger arrays alone do not
prove that execution is bandwidth-bound.

## Reproduction

Use the pinned CellPyLib install in [the initial pilot](cellpylib.md).

```sh
python -m pytest -q tests/test_cellpylib_multistate.py
python -m benchmarks.cellpylib_multistate --output docs/results/cellpylib-multistate.jsonl
```

JSONL starts with environment metadata; subsequent rows include raw timings,
8 x 8 warmup, SHA256, peak RSS, and exact two-buffer physical payload sizes.

## Results

152 backend measurements across 32 scenario groups; every group's output
hashes agree. Related regression tests: 94 passed. The full-history portion
contains 12 real CellPyLib comparisons; the 20 final-only groups are the
separate scale experiment described above.

Warm E2E milliseconds for 4096 x 4096 (16,777,216 cells), 3 updates:

| States / width | Rule | NumPy | Dense Numba | Packed | Word-aligned |
|---|---|---:|---:|---:|---:|
| 8 / 3bit | Totalistic | 275.1 | 172.6 | 2261.9 | 933.0 |
| 8 / 3bit | Cyclic | 104.6 | 236.9 | 1211.6 | 696.9 |
| 8 / 3bit | Transport | 25.0 | 37.1 | 377.9 | 208.1 |
| 32 / 5bit | Totalistic | 283.8 | 182.5 | 2309.4 | 876.4 |
| 32 / 5bit | Cyclic | 115.9 | 151.8 | 1314.2 | 568.8 |
| 32 / 5bit | Transport | 39.3 | 51.2 | 391.0 | 215.5 |

At 8192 x 8192 (67,108,864 cells), transport:

| States | Backend | Warm E2E | Peak RSS | Two state buffers |
|---|---|---:|---:|---:|
| 8 | NumPy | 106.4 ms | 359.9 MiB | varies |
| 8 | Dense Numba | 151.7 ms | 402.5 MiB | 128 MiB |
| 8 | Packed | 1557.3 ms | 457.8 MiB | 48 MiB |
| 8 | Word-aligned | 835.8 ms | 456.6 MiB | 48.8 MiB |
| 32 | NumPy | 169.8 ms | 359.8 MiB | varies |
| 32 | Dense Numba | 206.2 ms | 403.3 MiB | 128 MiB |
| 32 | Packed | 1564.9 ms | 514.8 MiB | 80 MiB |
| 32 | Word-aligned | 871.9 ms | 514.6 MiB | 85.3 MiB |

The storage savings are real, but do not yield lower process peak RSS in these
final-only E2E implementations. Dense input/output, allocation/conversion
transients, JIT and process memory all remain part of the measured workload.
RSS is not a direct measure of the two packed buffers. We have not attributed
each transient allocation with a native heap profiler.

No speed crossover was established by increasing grid size. Neither packed
layout beats both dense alternatives in these scenarios. Multiple packed
neighbor reads and read-modify-write stores remain expensive; word alignment
reduces that penalty but does not remove it. This evidence argues against
assuming that 3bit/5bit data or a large grid alone creates a speed advantage.

A next architectural experiment is packed long-lived storage plus row/tile
unpacking into small dense scratch buffers, reusing each unpacked neighbor for
many updates before repacking. This is a hypothesis, not a measured win.
Long-lived packed histories/checkpoints are another distinct capacity use
case, requiring a separate output contract from CellPyLib's dense history.
