# Native cached span bulk assignment

The [wrapper](../benchmarks/compressed_span_bulk_native.py) compares pinned
`589c0f0` Python bulk assignment against native bulk assignment from `15ca8c0`,
measured at checkout `e3ec755`. Both use the same freshly built native binary;
the pinned baseline still uses its earlier view-assignment path. The
[raw artifact](compressed-span-bulk-native-results.json) is unchanged. All measured
Python, harness, native-header and binary hashes matched across the run.

The historical 72-configuration harness is reused without editing its files.
It performs 32 partial 16-byte writes plus flush, 512 real changed values, four
3/5-bit direct/palette layouts, budgets 0/512/65536 and inside/outside/mixed traces,
none/ZSTD plus dense ZSTD. The additional 64 configurations perform 128 inside-only
writes of 1/16/64/256 bytes across the four layouts, budgets 512/65536 and both
codecs. Every assigned value differs at that moment. All methods receive the
same scalar prewarm; construction and full verification are outside timing.
Five paired repetitions randomize method order. Sixteen focused smoke tests pass.

All 136 configurations pass logical output, flush/clear/reload and cache checks.
After measurement, every paired sample was additionally checked: `stored_bytes`
and `cache_bytes` are identical before, after and after reload across baseline
and native. This confirms unchanged measured hot/cold sizes, not necessarily
byte-for-byte representation identity. Graph fields include referenced native
buffers and metadata, exclude shared runtime, codec scratch and allocator arenas,
and are not RSS. Dense receives prevalidated bytes and performs one byte-slice
assignment per touched chunk; its helper lacks full public API validation.

## Existing inside-write workload

Milliseconds for 32 writes + flush. Dense uses ZSTD level5/BITSHUFFLE/typesize1,
one thread. Equal cache budgets bound payload, not process memory.

| Layout | Budget | Codec | Python | Native | Dense ZSTD |
|---|---:|---|---:|---:|---:|
| direct-3bit | 512 | none | 0.055792 | 0.040833 | — |
| direct-3bit | 512 | zstd | 0.095500 | 0.078958 | 0.778167 |
| direct-3bit | 65536 | none | 0.059000 | 0.040959 | — |
| direct-3bit | 65536 | zstd | 0.093083 | 0.075625 | 0.038958 |
| palette-3bit | 512 | none | 0.071959 | 0.042833 | — |
| palette-3bit | 512 | zstd | 0.145958 | 0.105083 | 0.759250 |
| palette-3bit | 65536 | none | 0.076375 | 0.045125 | — |
| palette-3bit | 65536 | zstd | 0.131750 | 0.101500 | 0.041875 |
| direct-5bit | 512 | none | 0.056459 | 0.041625 | — |
| direct-5bit | 512 | zstd | 0.096708 | 0.079000 | 0.812209 |
| direct-5bit | 65536 | none | 0.056333 | 0.041958 | — |
| direct-5bit | 65536 | zstd | 0.097750 | 0.082417 | 0.043416 |
| palette-5bit | 512 | none | 0.088042 | 0.044916 | — |
| palette-5bit | 512 | zstd | 0.150334 | 0.106375 | 0.821916 |
| palette-5bit | 65536 | none | 0.086917 | 0.045417 | — |
| palette-5bit | 65536 | zstd | 0.156375 | 0.109958 | 0.044792 |

At 512-byte budget, native assignment improves none 1.36–1.96× and ZSTD 1.21–1.41×
over the already optimized Python span path. It preserves the compact hot span,
so it remains substantially faster than dense when the dense 4096-byte chunk does
not fit. At 65536 budget, dense ZSTD still wins: native 0.076–0.110 ms versus
dense 0.039–0.045 ms. Native packing reduces overhead but does not make packed
writes as cheap as direct byte-slice assignment plus a single final compression.

## Write-size batches

Milliseconds for 128 writes + flush, cache 65536. Changed values equal 128 times
write width. The full artifact also includes cache 512 for each of these rows.

| Layout | Bytes/write | Codec | Python | Native | Dense ZSTD |
|---|---:|---|---:|---:|---:|
| direct-3bit | 1 | none | 0.178625 | 0.130083 | — |
| direct-3bit | 1 | zstd | 0.201917 | 0.162917 | 0.090084 |
| direct-3bit | 16 | none | 0.198750 | 0.143792 | — |
| direct-3bit | 16 | zstd | 0.220584 | 0.162000 | 0.086958 |
| direct-3bit | 64 | none | 0.260167 | 0.149292 | — |
| direct-3bit | 64 | zstd | 0.286708 | 0.180000 | 0.088333 |
| direct-3bit | 256 | none | 0.534458 | 0.200875 | — |
| direct-3bit | 256 | zstd | 0.568875 | 0.239708 | 0.095416 |
| palette-3bit | 1 | none | 0.225583 | 0.141458 | — |
| palette-3bit | 1 | zstd | 0.296708 | 0.189500 | 0.088875 |
| palette-3bit | 16 | none | 0.249958 | 0.135292 | — |
| palette-3bit | 16 | zstd | 0.301750 | 0.188541 | 0.086875 |
| palette-3bit | 64 | none | 0.320958 | 0.152000 | — |
| palette-3bit | 64 | zstd | 0.371708 | 0.202375 | 0.086625 |
| palette-3bit | 256 | none | 0.595416 | 0.211583 | — |
| palette-3bit | 256 | zstd | 0.654834 | 0.264834 | 0.091917 |
| direct-5bit | 1 | none | 0.176250 | 0.140291 | — |
| direct-5bit | 1 | zstd | 0.208042 | 0.171375 | 0.095791 |
| direct-5bit | 16 | none | 0.197833 | 0.137917 | — |
| direct-5bit | 16 | zstd | 0.234375 | 0.173750 | 0.104542 |
| direct-5bit | 64 | none | 0.252666 | 0.150959 | — |
| direct-5bit | 64 | zstd | 0.297042 | 0.187625 | 0.094916 |
| direct-5bit | 256 | none | 0.517708 | 0.201625 | — |
| direct-5bit | 256 | zstd | 0.551292 | 0.239625 | 0.094542 |
| palette-5bit | 1 | none | 0.279500 | 0.133584 | — |
| palette-5bit | 1 | zstd | 0.343542 | 0.196166 | 0.104709 |
| palette-5bit | 16 | none | 0.326583 | 0.141417 | — |
| palette-5bit | 16 | zstd | 0.383042 | 0.199416 | 0.093083 |
| palette-5bit | 64 | none | 0.380250 | 0.158375 | — |
| palette-5bit | 64 | zstd | 0.434583 | 0.219000 | 0.101542 |
| palette-5bit | 256 | none | 0.635125 | 0.212625 | — |
| palette-5bit | 256 | zstd | 0.736333 | 0.277917 | 0.095292 |

None-codec speedup across layouts is 1.26–2.09× at 1 byte, 1.38–2.31× at 16,
1.67–2.40× at 64 and 2.57–2.99× at 256. Larger writes amortize fixed Python/public
API costs and benefit more from the native loop; palette translation gains are
particularly visible. Timings include final flush, so codec cost limits the
ZSTD ratios even when mutation itself becomes cheaper.

Fallback controls are approximately unchanged but include measured regressions:
cache 0 has median native/Python ratio 1.0015, range 0.934–1.085; outside/cache 512
median 1.008, range 0.984–1.029; outside/cache 65536 median 1.029, range 0.997–1.107.
These small absolute phases have variability; the artifact keeps all samples.
No universal no-regression claim follows. Mixed traces and every fallback row
are preserved in the nested 72-configuration results. This is a bounded synthetic
mutation study, not end-application throughput.

```sh
python -m benchmarks.compressed_span_bulk_native --output /tmp/native-bulk.json
python -m pytest -q tests/test_compressed_span_bulk_native_benchmark.py
```
