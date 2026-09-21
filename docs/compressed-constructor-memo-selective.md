# Selective constructor memoization experiment

Benchmark-only comparison; production is unchanged. The earlier prototype and its historical results remain intact. Every policy here uses pinned Python encoder `d90c7dd` with the same currently loaded native helpers.

The selective policy bypasses memoization entirely for `codec="none"` by constructing the unmodified baseline class. This deliberately loses the old policy's identical-chunk sharing benefit without a codec. For ZSTD, the pinned source loader injects one lookup immediately after the existing `_byte_palette(raw)` / uniform early return and before `direct_bits`. A cache hit still pays that native alphabet scan; a miss reuses its result. Uniform chunks never look up or enter the memo. The wrapper admits only immutable encoded bytes and removes the memo in `finally` when construction succeeds or fails.

The cache reserves 1,024 bytes for fixed helper metadata, 256 bytes per mapping entry, and exact `sys.getsizeof` key and record sizes. Payload accounting is incremental. Successful admission directly inserts into the dictionary and verifies its actual retained estimate; an unexpected reservation shortfall rolls back the insertion and shrinks the mapping, clearing it if necessary. This fallback is tested. It stops admissions when full and keeps existing entries available. Equality uses complete bytes keys, never digest-only matching. Python counters and dictionary metadata are included in the retained estimate; duplicate immutable records are conservatively counted repeatedly. Temporary insertion/rollback/encoding scratch is outside this retained budget and belongs to the separate peak-RSS measurement.

The experiment compares the baseline, original memo policy, and selective policy at 64 KiB, 256 KiB, and 1 MiB cache budgets. Inputs are 1 MiB with 4,096-byte chunks. Each constructor is timed five times with seeded randomized backend order. Exact encoded records, decoded bytes, and isolated edits after sharing are checked outside timing. The retained cold size is a reachable-object estimate, not RSS. Separate fresh processes measure peak RSS for identical and unique 32-state chunks; imports and input generation precede the baseline high-water mark. These single-worker RSS readings are descriptive, not precise allocation accounting.

Run:

```sh
python -m benchmarks.compressed_constructor_memo_selective --output docs/compressed-constructor-memo-selective-results.json
python -m benchmarks.compressed_constructor_memo_selective --memory --output docs/compressed-constructor-memo-selective-memory.json
```

Production/native/harness and prototype hashes are recorded before and after measurement. No application or training E2E speedup is claimed.

## Measured outcome

Five-repeat median whole-constructor milliseconds:

| Case | Codec | Baseline | Old 64K | Old 256K | Old 1M | Selective 64K | Selective 256K | Selective 1M |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| identical | none | 2.072 | 0.896 | 0.917 | 0.875 | 2.361 | 2.138 | 1.862 |
| identical | zstd | 11.076 | 0.875 | 0.890 | 0.919 | 0.866 | 0.841 | 0.833 |
| period31 | none | 0.986 | 1.375 | 1.090 | 1.035 | 0.984 | 0.973 | 0.955 |
| period31 | zstd | 7.625 | 5.335 | 1.963 | 1.878 | 5.060 | 1.775 | 1.902 |
| period67 | none | 0.976 | 1.667 | 1.342 | 1.296 | 0.975 | 0.975 | 1.009 |
| period67 | zstd | 8.381 | 7.859 | 3.673 | 3.366 | 7.509 | 3.493 | 3.195 |
| unique32 | none | 1.861 | 2.744 | 2.833 | 3.420 | 1.841 | 1.812 | 1.830 |
| unique32 | zstd | 11.308 | 12.178 | 12.715 | 13.130 | 12.125 | 12.215 | 12.427 |
| incompressible | none | 2.241 | 2.841 | 2.783 | 3.398 | 1.952 | 1.958 | 1.985 |
| incompressible | zstd | 12.668 | 13.553 | 13.360 | 14.599 | 13.462 | 13.492 | 13.758 |
| rare | none | 1.478 | 2.269 | 2.404 | 3.402 | 1.462 | 1.457 | 1.418 |
| rare | zstd | 13.327 | 14.369 | 14.137 | 15.748 | 13.384 | 14.061 | 14.570 |
| uniform | none | 0.300 | 1.084 | 1.268 | 1.747 | 0.308 | 0.300 | 0.307 |
| uniform | zstd | 0.293 | 1.062 | 1.372 | 1.675 | 0.324 | 0.350 | 0.340 |

The selective policy removes most uniform and unique-input overhead, but it is not universally faster. ZSTD unique32 still costs 7–10% more than the baseline; incompressible costs 6–9% more. Uniform ZSTD costs 11–19% more despite no memo lookup/admission, because the experimental wrapper and empty memo still have costs. Rare input has zero nonuniform hits, so its extra bookkeeping yields no benefit. Codec-none cases execute the same baseline implementation; their timing differences are measurement scatter and trivial factory overhead, not algorithmic improvements.

Repeated codec-backed chunks remain favorable: identical ZSTD is 12.8–13.3× faster and cold owned size drops from 667,049 to 5,452 bytes. Period31 with a 256 KiB cache is 4.30× faster; period67 with 1 MiB is 2.62× faster. Conservative reservations admit slightly fewer rotations near a limit (14 rather than 15 at 64 KiB), trading some hits/cold sharing for cheap bounded accounting. Identical none intentionally loses the old memo's roughly 2× constructor speedup and its cold-record deduplication.

For unique32 ZSTD, incremental peak RSS was 1,294,336 bytes for baseline and selective64K, versus 2,064,384 bytes for selective1M (old1M: 2,113,536). Identical ZSTD fell from 1,261,568 bytes baseline to 409,600 for either selective budget. Identical none remains 851,968 bytes under selective, whereas old memo measured 16,384–32,768 bytes. These are fresh-process incremental high-water measurements, not stable live-memory counts; the 1 MiB unique-input cache still adds a substantial temporary memory cost.

The default remains unchanged. The evidence supports explicit opt-in memoization for repetitive codec-backed data; it does not justify universal constructor caching. [Timing artifact](compressed-constructor-memo-selective-results.json) and [RSS artifact](compressed-constructor-memo-selective-memory.json) preserve all samples, counters, budgets, and source hashes. The original memo policy is rerun against the same pinned encoder here; its earlier historical artifact is not rewritten.
