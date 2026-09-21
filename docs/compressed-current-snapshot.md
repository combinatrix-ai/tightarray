# Current all-codec snapshot

This [fresh 84-row snapshot](compressed-current-snapshot-results.json) uses the
existing `benchmarks.compressed_storage` CLI, default 1 MiB, all sweeps, and
three repetitions. Current source includes cached span mutation `f9e2b93`.
Compare methods within this run; these are not ratios against historical runs.
Each row retains all raw repetitions. All exact operation checks, cache-budget
checks and built-in source guards passed. An external wrapper also checked all
`_compressed*.h` headers, `_core*.so` binary, Python implementation and harness
before/after the CLI, adding those hashes and a provenance note to the JSON.
The preserved artifact otherwise retains the CLI results unchanged.

Six base datasets and six sweep configurations are each evaluated with NumPy,
plain packed Array, adaptive none/LZ4/ZSTD and dense LZ4/ZSTD. Datasets/traces
use seeds 812/914; method order rotates by case/repeat. Dense codecs use level5,
BITSHUFFLE, typesize1, one thread. Operations comprise construction, 256 local,
medium and global scalar reads, 64 block reads of 64 bytes, and 64 updates plus
flush. Local/medium sets are prewarmed. Updates are drawn from the observed
alphabet and may include unchanged values; this is not the targeted all-changed
[span mutation experiment](compressed-span-updates.md).

Cold owned bytes use the standard harness's retained-graph estimate, including
metadata and referenced buffers. They are not payload-only bytes or RSS and
exclude allocator capacity, scratch and shared runtime. Backend accounting
implementations are estimates rather than a native allocation census. The
JSON also preserves payload/cache figures and all warm phases.

## Default chunk 4096/cache 65536

Cold owned bytes and median milliseconds:

| Case | Backend | Cold owned | Build | Local reads | Global reads | Updates + flush |
|---|---|---:|---:|---:|---:|---:|
| random8 | palette-none | 405033 | 2.281 | 0.083 | 0.493 | 0.521 |
| random8 | palette-lz4 | 405024 | 6.661 | 0.083 | 0.449 | 1.544 |
| random8 | palette-zstd | 405017 | 11.492 | 0.082 | 0.463 | 2.714 |
| random8 | dense-lz4 | 423323 | 2.723 | 0.079 | 1.245 | 0.976 |
| random8 | dense-zstd | 420243 | 5.252 | 0.072 | 1.352 | 1.744 |
| random32 | palette-none | 667105 | 2.244 | 0.086 | 0.517 | 0.994 |
| random32 | palette-lz4 | 667096 | 8.182 | 0.098 | 0.669 | 1.772 |
| random32 | palette-zstd | 667089 | 14.269 | 0.082 | 0.477 | 2.944 |
| random32 | dense-lz4 | 686187 | 2.700 | 0.075 | 1.138 | 0.975 |
| random32 | dense-zstd | 682339 | 6.900 | 0.077 | 1.228 | 1.865 |
| local-two | palette-none | 143273 | 2.922 | 0.107 | 0.274 | 1.400 |
| local-two | palette-lz4 | 143272 | 11.131 | 0.080 | 0.326 | 3.113 |
| local-two | palette-zstd | 143273 | 109.858 | 0.083 | 0.273 | 24.913 |
| local-two | dense-lz4 | 259451 | 2.776 | 0.068 | 1.070 | 1.107 |
| local-two | dense-zstd | 257448 | 5.061 | 0.067 | 1.182 | 1.635 |
| uniform-chunks | palette-none | 7209 | 0.304 | 0.063 | 0.060 | 0.869 |
| uniform-chunks | palette-lz4 | 7208 | 0.317 | 0.066 | 0.059 | 2.293 |
| uniform-chunks | palette-zstd | 7209 | 0.301 | 0.065 | 0.061 | 2.869 |
| uniform-chunks | dense-lz4 | 31741 | 2.503 | 0.067 | 1.043 | 0.900 |
| uniform-chunks | dense-zstd | 29231 | 3.260 | 0.067 | 1.290 | 1.399 |
| runs32 | palette-none | 75171 | 1.243 | 0.081 | 0.839 | 0.521 |
| runs32 | palette-lz4 | 75170 | 7.638 | 0.080 | 0.805 | 1.875 |
| runs32 | palette-zstd | 75171 | 74.060 | 0.079 | 0.795 | 16.451 |
| runs32 | dense-lz4 | 278016 | 3.575 | 0.068 | 1.409 | 1.316 |
| runs32 | dense-zstd | 80001 | 41.066 | 0.069 | 1.828 | 10.288 |
| rare-spikes | palette-none | 18536 | 1.433 | 0.083 | 0.516 | 0.954 |
| rare-spikes | palette-lz4 | 18535 | 8.620 | 0.080 | 0.517 | 2.671 |
| rare-spikes | palette-zstd | 18536 | 13.011 | 0.079 | 0.525 | 3.769 |
| rare-spikes | dense-lz4 | 46771 | 2.613 | 0.067 | 1.051 | 0.884 |
| rare-spikes | dense-zstd | 37746 | 5.005 | 0.072 | 1.209 | 1.663 |

For these six configurations, adaptive none/LZ4/ZSTD have effectively identical
cold retained size (one-digit metadata differences are not compression gains).
Extra codec trials nevertheless cost substantially. Local-two ZSTD construction
is 21.7× slower than dense ZSTD and updates 15.2× slower, while retained memory is
44.3% smaller and global reads 4.3× faster. The same adaptive capacity is obtained
without a codec in 2.922 ms construction and 1.400 ms updates. Runs32 likewise
uses 75171 bytes with or without adaptive codecs, while none construction/update
are 1.243/0.521 ms versus ZSTD 74.060/16.451 ms. Dense ZSTD retains 80001 bytes.

Dense cached local reads generally beat adaptive cached local reads by a small
absolute amount; cold global reads favor adaptive for all six base datasets.
Plain packed arrays are much faster still when a global alphabet is suitable:
random8 packed uses 393288 bytes, builds in 0.218 ms and performs global reads
in 0.013 ms; adaptive none uses 405033 bytes, 2.281 ms and 0.493 ms. NumPy uses
1048688 bytes there but remains faster for construction and many operations.
Adaptive representation is justified by local alphabets/structure/capacity,
not as an unconditional replacement for a single packed buffer.

## Alignment and cache sweeps

The generator's local-two regions remain 4096 bytes while storage chunks vary.
At 16384 bytes a storage chunk crosses four independent two-label regions. Codec
work now buys real capacity, so simply disabling codecs is not equivalent:

| Backend, local-two chunk 16384 | Cold owned | Build ms | Global ms | Updates ms |
|---|---:|---:|---:|---:|
| palette-none | 397054 | 2.660 | 0.421 | 4.802 |
| palette-lz4 | 241984 | 7.026 | 3.365 | 8.580 |
| palette-zstd | 196611 | 110.649 | 4.172 | 109.182 |
| dense-lz4 | 241956 | 1.129 | 2.968 | 1.734 |
| dense-zstd | 238092 | 3.602 | 3.197 | 3.894 |

Adaptive ZSTD retains 17.4% less than dense ZSTD here, but construction is 30.7×
slower, updates 28.0× slower, and global reads also lose. Adaptive LZ4 retains
essentially the same amount as dense LZ4 while costing more in all three phases.
The remaining gap is genuine codec/selection work, not only Python scalar access.

Larger random8 chunks amortize metadata/construction: adaptive none at 16384 uses
396553 bytes and builds in 1.068 ms, versus 438441 bytes and 4.762 ms at 1024.
Dense ZSTD global reads grow from 0.700 to 3.279 ms across those sizes while adaptive
none grows from 0.382 to 0.497 ms. With cache 0, uniform adaptive global reads stay
near0.06 ms because constants need no decompression; random8 adaptive none is
0.251 ms versus dense ZSTD 1.274 ms. Write-through still makes codec updates costly.

These synthetic results identify useful work: avoid repeating unproductive
codec work without sacrificing the chunk 16384 capacity benefit, retain the
locality-aware hot cache, and compare applications against ordinary packed
storage as well as dense codecs. Results do not justify skipping codecs based
on an unproven incompressibility heuristic. The three repetitions capture
bounded evidence and some timing variability, not a universal performance claim.

```sh
python -m benchmarks.compressed_storage --repeats 3 --output /tmp/current.json
```

The reproduction command includes the standard guards; the additional native
header/binary guard was supplied by the external wrapper described above.

## All twelve configurations against dense ZSTD

Ratios are adaptive ZSTD / dense ZSTD from this same batch. Below1 means
less memory or less time; above1 means more. This compares matching codec
settings, not the fastest adaptive choice (none is often faster).

| Case | Chunk/cache | Cold owned | Build | Local | Medium | Global | Read64 | Update |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| random8 | 4096/65536 | 0.96 | 2.19 | 1.14 | 0.08 | 0.34 | 0.47 | 1.56 |
| random32 | 4096/65536 | 0.98 | 2.07 | 1.07 | 0.26 | 0.39 | 0.43 | 1.58 |
| local-two | 4096/65536 | 0.56 | 21.71 | 1.25 | 0.11 | 0.23 | 0.33 | 15.23 |
| uniform-chunks | 4096/65536 | 0.25 | 0.09 | 0.97 | 0.08 | 0.05 | 0.13 | 2.05 |
| runs32 | 4096/65536 | 0.94 | 1.80 | 1.13 | 0.32 | 0.43 | 0.51 | 1.60 |
| rare-spikes | 4096/65536 | 0.49 | 2.60 | 1.09 | 0.11 | 0.43 | 0.45 | 2.27 |
| random8 | 1024/65536 | 0.88 | 2.18 | 1.12 | 1.07 | 0.47 | 0.57 | 1.96 |
| random8 | 16384/65536 | 0.99 | 1.91 | 0.05 | 0.12 | 0.13 | 0.16 | 1.45 |
| local-two | 1024/65536 | 0.52 | 8.82 | 1.18 | 1.07 | 0.47 | 0.58 | 7.38 |
| local-two | 16384/65536 | 0.83 | 30.72 | 1.33 | 1.49 | 1.30 | 1.25 | 28.04 |
| random8 | 4096/0 | 0.96 | 2.03 | 0.22 | 0.22 | 0.21 | 0.29 | 1.97 |
| uniform-chunks | 4096/0 | 0.25 | 0.09 | 0.05 | 0.05 | 0.05 | 0.13 | 2.46 |
