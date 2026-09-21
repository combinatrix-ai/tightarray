# Context reuse in current update and flush workloads

This study reuses the existing experimental `SharedContextPool`, without changing
production. [Phase measurements](compressed-context-phases-results.json) include
56 configurations, each with 31 randomized trials of four modes: current adaptive,
dense comparator, shared pool cold, and shared pool warmed by construction. Each
fresh array receives 32 actually changing 16/256-byte writes and a flush; construction
and prewarming are excluded. Cold clears the pool before timing, warm retains its
constructor contexts. Exact adaptive cold hashes agree across all modes and trials;
values survive flush/cache clear/reload. Source guards passed.

Median total-time ratios across configurations:

| Cache payload budget | Codec | Cold pool / adaptive | Warm pool / adaptive | Warm pool / dense |
|---|---|---:|---:|---:|
| 512 | LZ4 | 0.896 | 0.865 | 1.764 |
| 512 | ZSTD | 0.914 | 0.906 | 1.733 |
| 65536 | LZ4 | 1.477 | 0.959 | 2.072 |
| 65536 | ZSTD | 1.311 | 0.958 | 2.010 |

Small-cache ordinary arrays repeatedly encode, amortizing context setup. A fitting
cache defers compression until flush, so creating SChunks for that single flush
costs more than ordinary compression. Warm reuse helps but does not generally beat
the dense comparator. Compact span cases remain exceptions where adaptive caching
avoids repeated compression. Dense receives prevalidated bytes and has less input
validation than the public adaptive API. Budgets constrain payload, not RSS.

The [fresh-process memory samples](compressed-context-memory-current.json) reproduce
the previous RSS concern. At 16 arrays, RSS growth was 0.469 MiB for ordinary calls
versus 2.094 MiB for an 18-entry shared pool. At 100 arrays, 0.781 versus 1.688 MiB;
at 500 arrays, 2.031 versus 3.547 MiB. These are single fresh-process samples per
configuration, not confidence intervals. Allocator retention and native workspaces
are included in RSS and excluded from array-owned graph accounting. Shared contexts
are bounded by count and input length, not by a trustworthy native-byte bound.

Decision: do not adopt this SChunk pool as the default. It offers a speed/memory
tradeoff, with substantial cold-start costs. Separate experimental lifecycle work
addresses fork reset but is not included in these timings. A compression-only
public-C context prototype is the next way to test whether SChunk metadata and
decoder context can be avoided. No private bounded-output API is used.

Four smoke tests cover both cache budgets/codecs and exact cold-record equality,
plus cold/warm context state. The timing artifact uses the original pool, whose
inherited contexts/locks are explicitly unsupported across fork.

The separate `compressed_context_lifecycle` experiment adds weakly registered fork
hooks and waits for pool operations to become quiescent before forking, then gives
the child empty contexts and fresh locks. Six lifecycle tests cover both codecs,
failure discard, bounded keys, weak registration and timeout-isolated real fork/
thread cases. All 15 phase/lifecycle/original-pool tests and Ruff passed together.
This wrapper adds synchronization not included in the timing figures above. It
does not make arbitrary concurrent Blosc work fork-safe; a hung pool operation can
delay fork indefinitely. Production remains unchanged.

```sh
python -m pytest tests/test_compressed_context_phases.py
python -m benchmarks.compressed_context_phases --repeats 31 --output phases.json
python -m benchmarks.compressed_context_phases --memory --output memory.json
```
