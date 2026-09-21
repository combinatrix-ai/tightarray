# Public bulk update and flush phases

Measured production at `99377a7`, with its current native binary. This is a phase breakdown against matching dense codecs, not a before/after optimization claim. The unchanged [raw artifact](compressed-bulk-phases-results.json) records all 84 configurations, 31 trials each, separate untimed counters, and 16 source/binary hashes. Source guards passed.

Each fresh 4096-element array receives the same scalar prewarm followed by 32 actually changing writes of 16 or 256 bytes, then a flush. Construction and verification are outside timing. Update, flush and total use consecutive timer boundaries; medians of phases need not sum to the median total. Trial backend order is randomized with seed 742. Values, flush/reload and cache bounds are checked each trial. Data seed is 734; ordinary trace seed is 735 plus write width. The span trace stays inside its 512-element random interior. These are repeated trials within one process, not independent-machine replications.

Cases cover random direct 3/5/8-bit values, high-label 3/5-bit palettes, a periodic array, and a zero-padded random span. Cache budgets are 512 and 65536 bytes. Adaptive runs none/LZ4/ZSTD; dense runs matching LZ4/ZSTD. The dense helper uses chunk-wise bytearray slice updates with prevalidated bytes and lacks full public input validation. Both budgets constrain retained cache payload, not RSS. Both codecs use level 5, typesize 1 and one thread. Dense uses BITSHUFFLE; adaptive compares BITSHUFFLE raw bytes and NOFILTER packed candidates. Exact settings remain in the guarded production and harness sources.

## Fitting-cache phases

The following medians are milliseconds for all 32 writes, with a 65536-byte cache and 16-byte writes. Full 256-byte and small-cache results remain in the artifact.

| Layout | Codec | Adaptive update | Adaptive flush | Dense update | Dense flush | Adaptive flush compression calls |
|---|---|---:|---:|---:|---:|---:|
| direct-3bit | none | 0.0252 | 0.0072 | — | — | 0 |
| direct-3bit | lz4 | 0.0265 | 0.0263 | 0.0176 | 0.0113 | 2 |
| direct-3bit | zstd | 0.0265 | 0.0419 | 0.0176 | 0.0190 | 2 |
| direct-5bit | none | 0.0254 | 0.0079 | — | — | 0 |
| direct-5bit | lz4 | 0.0268 | 0.0278 | 0.0175 | 0.0115 | 2 |
| direct-5bit | zstd | 0.0267 | 0.0460 | 0.0175 | 0.0212 | 2 |
| direct-8bit | none | 0.0245 | 0.0080 | — | — | 0 |
| direct-8bit | lz4 | 0.0257 | 0.0253 | 0.0174 | 0.0110 | 2 |
| direct-8bit | zstd | 0.0261 | 0.0492 | 0.0176 | 0.0222 | 2 |
| palette-3bit | none | 0.0265 | 0.0113 | — | — | 0 |
| palette-3bit | lz4 | 0.0275 | 0.0410 | 0.0177 | 0.0115 | 3 |
| palette-3bit | zstd | 0.0271 | 0.1258 | 0.0177 | 0.0193 | 3 |
| palette-5bit | none | 0.0266 | 0.0127 | — | — | 0 |
| palette-5bit | lz4 | 0.0273 | 0.0382 | 0.0177 | 0.0115 | 3 |
| palette-5bit | zstd | 0.0268 | 0.0771 | 0.0174 | 0.0207 | 3 |
| periodic-control | none | 0.0299 | 0.0085 | — | — | 0 |
| periodic-control | lz4 | 0.0314 | 0.0307 | 0.0178 | 0.0129 | 2 |
| periodic-control | zstd | 0.0346 | 0.1971 | 0.0188 | 0.0871 | 2 |
| span-control | none | 0.0252 | 0.0086 | — | — | 0 |
| span-control | lz4 | 0.0259 | 0.0300 | 0.0173 | 0.0111 | 2 |
| span-control | zstd | 0.0260 | 0.0449 | 0.0173 | 0.0212 | 2 |

For ordinary direct and palette arrays, fitting-cache ZSTD updates take about 0.026–0.027 ms at 16 bytes; their flushes take 0.042–0.126 ms. Dense updates are about 0.018 ms and flushes 0.019–0.022 ms. Adaptive performs one encode at flush but evaluates two direct or three palette compression candidates, versus one dense encode/compression. The adaptive candidate inputs total 5632/6656/8192 bytes for direct 3/5/8-bit and 9728/10752 bytes for palette 3/5-bit. These counts include attempted candidates that are not retained.

Codec-free flushes for those layouts take 0.007–0.013 ms. This supports investigating cold encoding and codec-call overhead; it does not isolate codec setup from compression, filtering, packing or candidate planning. Periodic writes destroy the original exact period, so this control also measures the cost of encoding the modified data.

At 256-byte writes, direct 3/5-bit and palette cached updates rise to 0.043–0.046 ms; direct 8-bit remains about 0.026 ms. There is therefore residual packed mutation work as well as flush work.

## Cache-capacity difference

At a 512-byte budget the ordinary packed chunks do not fit. All 32 writes encode immediately: adaptive makes 64 direct or 96 palette compression calls, while dense makes 32. The final flush does effectively no work. ZSTD update totals are 1.36–1.67 ms for direct cases and 2.82–4.41 ms for palette cases, versus 0.73–0.82 ms dense. Moving work out of the final flush is not a speedup: the same encoder is now invoked repeatedly during updates.

The span retains a 320-byte hot representation at that same budget. It does zero compression during updates and two calls at its one final encode. Total ZSTD times are 0.0751/0.0890 ms for 16/256-byte writes versus dense 0.8189/0.8143 ms: about 10.9×/9.1× faster. Dense cannot retain its 4096-byte decoded chunk. At a fitting 65536-byte budget dense wins instead: 0.0383/0.0389 ms versus adaptive 0.0709/0.0887 ms.

After the 16-byte ZSTD span workload, adaptive owns a measured reachable object graph of 2387 bytes (326 stored payload, 320 hot payload). Dense at cache512 owns 1640 bytes with no hot payload, or 6105 bytes at cache65536 with 4096 hot bytes. Adaptive spends more retained memory than uncached dense in the first comparison to avoid repeated decompression/encoding; this is not a universal memory win. Shared modules, native scratch/allocator retention and RSS are outside the reachable-graph accounting. Before/after/reloaded values are retained for every trial.

## Reproduction

```sh
python -m pytest tests/test_compressed_bulk_phases.py
python -m benchmarks.compressed_bulk_phases --repeats 31 --output phases.json
```

Six smoke tests check phase accounting, exact mutation/reload, cache bounds and fitting/non-fitting encode counts. Compression counters run only in a separate instrumented pass; the timed classes are uninstrumented. The script measures the checkout in which it runs, so reproducing this historical result requires the recorded source/binary versions. No production code was changed by this study.
