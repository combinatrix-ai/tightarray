# Constructor-only exact memoization prototype

**Repeated expensive chunks benefit substantially; unique and already-cheap chunks lose.** This remains a benchmark prototype, not a production default or API. It compares pinned Python `compressed.py` at `65c7a89` using the currently compiled native helpers. Source and native-binary hashes were unchanged across both runs.

The baseline still evaluates all codec candidates. The memo reuses the final immutable record only for an exactly equal complete input chunk. Python dictionaries hash keys but confirm byte equality; digest collisions cannot cause a wrong record. Encoded records match baseline byte-for-byte. Editing the first chunk and flushing preserves every other chunk, including when cold records share the same bytes object.

## Method

Each case has 1 MiB of logical uint8 data in 256 chunks of 4096 bytes. The identical case repeats one seeded random32 chunk. Period31/67 cases cycle their pattern through chunk boundaries, giving 31/67 distinct rotations. Unique32 and incompressible are independent random data. Rare and uniform reuse the standard seeded storage fixtures. Both none and ZSTD codecs are tested.

Time covers the entire constructor, including cache creation, lookup, admission bookkeeping and cleanup. Five repetitions use shuffled backend order. Verification and mutation-isolation checks occur outside timing. Unlike a general runtime cache, the memo is removed when construction returns; later writes do not consult it. Cleanup also runs when construction raises.

Admission is FIFO: when the cache first exceeds its budget, it stops admitting new keys while retaining old entries. No eviction occurs. The conservative retained-byte estimate includes the helper, dictionary metadata, complete input-byte keys, final records and scalar bookkeeping; shared values are counted repeatedly. Admission stages a temporary dictionary copy and publishes it only if it fits. **That staging scratch, input data and codec scratch are outside the retained-cache budget**, so this budget is not a process-memory limit. Hit accounting is constant-time; staged admission copying can penalize unique inputs. The prototype intentionally exposes that cost rather than comparing only idealized cache hits.

## Whole-construction timings

| Case | Codec | Baseline ms | 64 KiB ms | 256 KiB ms | 1 MiB ms |
|---|---|---:|---:|---:|---:|
| identical | none | 1.810 | 0.871 | 0.850 | 0.850 |
| identical | zstd | 11.032 | 0.901 | 0.911 | 0.876 |
| period31 | none | 1.007 | 1.367 | 1.064 | 1.011 |
| period31 | zstd | 7.199 | 5.220 | 1.813 | 1.869 |
| period67 | none | 0.994 | 1.701 | 1.351 | 1.338 |
| period67 | zstd | 8.138 | 7.724 | 3.595 | 3.404 |
| unique32 | none | 1.804 | 2.646 | 2.694 | 3.265 |
| unique32 | zstd | 11.327 | 12.627 | 12.398 | 13.185 |
| incompressible | none | 1.966 | 2.974 | 2.854 | 3.373 |
| incompressible | zstd | 12.631 | 13.398 | 13.621 | 14.452 |
| rare | none | 1.431 | 2.224 | 2.508 | 3.591 |
| rare | zstd | 13.111 | 14.106 | 14.338 | 15.161 |
| uniform | none | 0.290 | 1.068 | 1.255 | 1.652 |
| uniform | zstd | 0.296 | 1.088 | 1.261 | 1.708 |

A 64 KiB cache hits 255 of 256 identical chunks and reduces ZSTD construction from 11.032 to 0.901 ms (about 12.2×). At 256 KiB, all 31 rotations fit: 225 hits reduce period31 ZSTD time from 7.199 to 1.813 ms. Period67 needs approximately 285 KB retained memo storage to fit all 67 rotations, so the 1 MiB budget wins more than256 KiB.

The losses are material. Unique32 has zero hits and grows from 1.804 to 3.265 ms without a codec at the 1 MiB budget; ZSTD grows from 11.327 to 13.185 ms. Incompressible and rare inputs also lose. Uniform chunks have hits but their original encoding is so cheap that memo bookkeeping dominates: approximately 3.7–5.8× slower. None-codec periodic cases also mostly lose despite retained-memory savings.

## Retained cold storage and peak RSS

Memo entries are cleared at constructor exit, but equal immutable cold records can remain shared. For identical chunks, estimated cold retained storage falls from about 667 KB to 5.4 KB; logical `stored_bytes` still sums the per-chunk records and therefore does not represent shared physical ownership. At 256 KiB cache budget, period31 retained storage falls from 18.1 KB to 4.6 KB. Unique cases receive no such benefit and retain an approximately 8-byte object-layout difference in this run. These are `sys.getsizeof`-based retained-graph estimates, not RSS.

Separate fresh processes measured peak RSS after imports, source generation and codec-module initialization, then after construction. The table reports **incremental high-water growth**; it is not live allocation size, and one process per configuration does not establish a stable statistical RSS difference.

| Case | Codec | Baseline KiB | 64 KiB cache | 1 MiB cache |
|---|---|---:|---:|---:|
| identical | none | 848 | 16 | 16 |
| identical | zstd | 1216 | 400 | 400 |
| unique32 | none | 832 | 864 | 1632 |
| unique32 | zstd | 1296 | 1344 | 2032 |

Identical records benefit from sharing and reduced codec work. For unique inputs, a 1 MiB memo budget adds roughly 0.7–0.8 MiB incremental peak growth in these observations. Absolute peak RSS, including the approximately 60 MB runtime/input baseline, is retained in the raw artifact. Allocator reuse and earlier high-water marks can affect these deltas. No claim is made that clearing the memo returns pages to the OS.

## Decision and reproduction

This supports an explicit constructor optimization for known repetitive inputs, especially codec-backed data, rather than unconditional memoization. A future optimization might bypass trivial uniform records and disable admission after poor hit rates, but that policy is **untested**. Memo admission machinery itself also needs profiling before adopting a production implementation.

```sh
python -m benchmarks.compressed_constructor_memo --output /tmp/memo-times.json
python -m benchmarks.compressed_constructor_memo --memory --output /tmp/memo-rss.json
pytest -q tests/test_compressed_constructor_memo.py
```

[Timing and retained-cache measurements](compressed-constructor-memo-results.json) · [Fresh-process peak RSS](compressed-constructor-memo-memory.json) · [Prototype](../benchmarks/compressed_constructor_memo.py)
