# Codec-free SIMD writes versus cached Blosc2

Production `9f72f0c` native kernel, CPython3.12 ARM64, Python-Blosc2 4.13.1. Same-run comparison of one 4096-element chunk, fitting65536-byte cache,32 actually changed contiguous writes at seeded scattered positions, then one flush. Construction is excluded; one read prewarms the cache. Nine trials rotate backend order. Exact reads and reloads match. No general throughput or full Blosc2 NDArray claim is made.

Blosc2 uses the existing benchmark's custom decoded uint8 LRU with contiguous slice writes, clevel5, BITSHUFFLE, typesize1 and one thread. Its helper does less API validation than CompressedArray. These are small hot-cache batches; repeated writes amortize compression into one flush. Cache pressure and read-heavy workloads can change the result.

Median across direct3/5-bit and palette3/5-bit case ratios, tightarray time / comparator time (above1 means tightarray slower):

| Values per write | Updates vs LZ4 | Updates vs ZSTD | Updates+flush vs LZ4 | Updates+flush vs ZSTD |
|---:|---:|---:|---:|---:|
|64|1.740|1.704|1.341|0.968|
|256|2.001|2.037|1.498|1.093|
|1024|2.529|2.534|1.885|1.423|

Example direct5-bit,1024 values per write,32 writes:

| Method | Updates microseconds | Updates+flush microseconds | Cached payload bytes | Cold retained graph bytes |
|---|---:|---:|---:|---:|
|tightarray codec none|39.542|46.792|2560|3268|
|Blosc2 LZ4|17.500|27.958|4096|3441|
|Blosc2 ZSTD|17.375|37.250|4096|3426|

The SIMD improvement versus old tightarray does not imply a win against decoded uint8 slice assignment. Packing retains a smaller hot representation, while Blosc2 writes into expanded bytes and compresses only at flush. Retained graph bytes include benchmark-accounted metadata and are not RSS; hot payload excludes other retained state. Dense8 is an unchanged control, included in raw results but excluded from narrow-width aggregate ratios.

[Raw samples and source guards](compressed-simd-blosc-results.json). Reproduce with `python -m benchmarks.compressed_simd_blosc`. All15 case/width groups and405 timed trials passed data/cache-clear verification. No production code changed for this comparison.
