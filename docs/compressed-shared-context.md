# Experimental bounded shared compression contexts

This is a benchmark prototype, not a production API or a default change.
`benchmarks/compressed_shared_context.py` temporarily replaces `_compress`
inside its own process; exhaustive candidate generation and selection remain
unchanged. It retains at most 18 contexts, for payloads no larger than 4096
bytes, shared across arrays. Keys include codec, filter and exact payload size.

A short metadata lock protects checkout and return. Compression runs outside
the lock. Busy keys, full pools and oversized buffers use ordinary `compress2`.
Native failures discard the checked-out context. The pool has no replacement
policy: unfamiliar shapes fall back after capacity is reached. Returned chunk
bytes are independent copies. There is no fork reset hook; **fork inheritance
of the pool is unsupported**. Child workers must construct a fresh pool.

## Measured tradeoff

Six cases from `compressed_storage.dataset`, each 1 MiB, both LZ4 and ZSTD,
four independent arrays per sample, three repeats with seeded randomized mode
order. Each operation constructs the arrays, performs 32 scalar writes per
array, and flushes. All cold encoded chunks match baseline bytes exactly;
logical output is checked outside timing. Timings include every candidate.

| Sum of six per-case medians | compress2 | Shared cold | Shared warm |
|---|---:|---:|---:|
| LZ4 | 161.55 ms | 133.25 ms | 132.86 ms |
| ZSTD | 1011.49 ms | 942.40 ms | 938.95 ms |

These correspond to about 1.21× and 1.07× throughput with a cold shared pool.
The cold path includes native-context initialization. The warm path runs one
untimed matching workload first. The trivial Python pool wrapper is allocated
before the timer in both cases. There is no claim that all workloads improve
by those aggregate factors.

Fresh processes independently measured current RSS before/after construction:

| Arrays | compress2 RSS increase | Shared RSS increase |
|---|---:|---:|
| 16 | 0.57 MB | 2.20 MB |
| 100 | 0.80 MB | 2.18 MB |
| 500 | 2.23 MB | 3.05 MB |

Inputs cycle through all eight physical widths and both codecs. The shared
pool reaches 18 contexts and stays there. These process deltas include native
scratch, allocator behavior and Python bookkeeping; they are **not exact
context-allocation sizes**. Array-owned accounting excludes shared contexts.
Clearing arrays and contexts did not immediately reduce RSS on this run.
Unlike a separate pool per array, the observed overhead does not grow linearly
with array count, but a count bound is not a byte/RSS bound.

Five focused tests cover compressed-byte equality, retained-output ownership,
busy-key fallback without blocking unrelated keys, failure cleanup, and four
threads operating on eight arrays with Blosc2 GIL release enabled.

## Reproduction and provenance

```sh
python -m benchmarks.compressed_shared_context --output /tmp/shared-timing.json
python -m benchmarks.compressed_shared_context --memory --output /tmp/shared-rss.json
pytest -q tests/test_compressed_shared_context.py
```

The JSON files below are copied unchanged from this prototype's measured runs.
They are coupled to the working-tree implementation used then; they do not claim
a later source hash. The script contains the dataset/order seeds and exact
parameters. RSS uses `ps` in fresh workers and may need process-inspection
permission in a sandbox. Results do not establish a deployment default.

- [Timing samples and pool counters](compressed-shared-context-timing.json)
- [Fresh-process RSS observations](compressed-shared-context-memory.json)

Before production adoption, an explicit runtime-pool lifecycle, fork handling,
concurrency contract and shared-memory accounting are required. The measured
tradeoff supports further consideration, not unconditional pooling.
