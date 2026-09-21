# Compression-only native context experiment

This uses the disposable public-C extension from `benchmarks/native_context`,
not production tightarray. The new adapter gives the existing bounded shared
pool a compression-only context and releases its temporary compressed bytes
after each call. Unlike SChunk it retains no chunk payload, decoder context or
chunk index. The pool still has Python locking/counters and an 18-context limit,
with exact codec/filter/input-length keys and ordinary compression fallback.
Inherited pools remain unsupported across fork in this experiment.

The [phase data](compressed-ccontext-phases.json.gz) and
[memory data](compressed-ccontext-memory.json.gz) are lossless gzip copies of
the original JSON outputs. Source/binary hashes are retained. All adaptive cold
records match across methods and trials; logical values are checked after flush
and cache clear/reload. There are 56 phase configurations × 31 randomized trials
of six methods. Construction/prewarming are excluded, then 32 actually changing
16/256-byte writes plus flush are timed. Cold clears contexts before updates;
warm retains contexts created during construction. The same separate native
library image is loaded throughout timing. These are single-process timing
trials, not independent-process timing replications.

Median total-time ratios across configurations:

| Cache bytes | Codec | Native cold / adaptive | Native warm / adaptive | Native warm / dense |
|---|---|---:|---:|---:|
| 512 | LZ4 | 0.809 | 0.805 | 1.686 |
| 512 | ZSTD | 0.854 | 0.869 | 1.693 |
| 65536 | LZ4 | 0.940 | 0.906 | 1.922 |
| 65536 | ZSTD | 0.963 | 0.921 | 1.996 |

This removes most of SChunk's cold-start penalty: at the fitting cache budget,
SChunk cold ratios were 1.490/1.329 for LZ4/ZSTD in this same run. Nevertheless,
the native pool is not universally faster (fitting-cache ZSTD maxima 1.039 cold,
1.028 warm), and median performance still trails dense. The dense helper has
less public input validation, and the cache budget covers payload rather than
RSS. This experiment changes both the wrapper and library image, so it does not
isolate compression-context reuse alone. The native wrapper holds the GIL and
does not establish multithreaded throughput improvement.

Memory measurements use three fresh workers per mode/count (36 processes), with
randomized mode order. Every worker, including controls, first imports the native
extension so extra-image mapping is normalized. That import adds roughly 0.266
MiB median RSS before the workload. Subsequent median RSS growth in MiB:

| Arrays | Ordinary calls | SChunk pool | Native context pool |
|---|---:|---:|---:|
| 16 | 0.562 | 2.156 | 0.891 |
| 100 | 0.797 | 2.297 | 1.156 |
| 500 | 2.094 | 3.484 | 2.578 |

At 16 arrays native measurements ranged 0.688–1.188 MiB; at 500 arrays
2.156–2.781 MiB. These samples include allocator and scratch retention, not just
live contexts. No byte cap or stable memory guarantee follows from them. The
native pool reduces the earlier SChunk memory penalty but still costs memory,
and a real deployment must account for the separate-image import cost too.

Decision: promising experimental speed/memory improvement, not a production
default. The current wheel statically embeds Blosc in its Python extension;
this prototype loads an independently initialized dylib. Packaging/lifecycle,
error injection, sanitizers and broader workloads remain before adoption.
Prefer a supported compression-context interface using a single library image
if available. The remaining 2–3 compression candidates per encode still explain
much of the gap to the one-compression dense comparator.

Validation: 56 combined native-context, pool ownership, phase, lifecycle and
original shared-pool tests passed; Ruff and diff whitespace checks passed.
No production source or package build configuration changed.

Reproduction requires the disposable native build documented in its README:

```sh
PYTHONPATH=/tmp/ta-ccontext-lib python -m benchmarks.compressed_ccontext_study --repeats 31 --output phases.json
PYTHONPATH=/tmp/ta-ccontext-lib python -m benchmarks.compressed_ccontext_study --memory --repeats 3 --output memory.json
PYTHONPATH=/tmp/ta-ccontext-lib python -m pytest benchmarks/native_context/test_context.py benchmarks/native_context/test_pool.py
```
