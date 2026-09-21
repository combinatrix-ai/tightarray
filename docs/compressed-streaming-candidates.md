# Streaming cold candidate selection

Benchmark-only prototype; production was not changed by this study. Both policies use Python pinned at `d3596fd9899797f9e1dede772fbc1fb03300d9bd` and the same current native binary. The prototype retains the pinned planning prefix and replaces candidate objects/list/tuple/min selection with scalar winner fields. Codec attempts, candidate order, pruning thresholds and strict ties remain unchanged. The codec-free ordinary return also avoids its temporary `_Chunk`.

The [unchanged raw artifact](compressed-streaming-candidates-results.json) contains all samples and source/binary hashes. The script hash matches the measured script; two additional mutation-trace tests were added afterward. Source guards passed.

## Results

Ratios below are streaming median time / baseline median time; below 1 is faster. Each configuration has 11 balanced trials with seeded randomized policy order. Encode averages 100 calls on the first 4096-byte chunk, including its slice; build uses a fresh 65536-byte array; update+flush performs 32 actually changing 16-byte writes after construction and a scalar prewarm, with a 65536-byte cache. Construction is excluded from update timing. These are within-process repetitions, not independent-process replications.

| Case | Codec | Encode ratio | Build ratio | Update+flush ratio | Codec calls per build, both policies |
|---|---|---:|---:|---:|---:|
| direct-3 | none | 0.895 | 0.898 | 0.942 | 0 |
| direct-3 | lz4 | 0.846 | 0.852 | 0.886 | 32 |
| direct-3 | zstd | 0.899 | 0.843 | 0.922 | 32 |
| direct-5 | none | 0.908 | 0.904 | 0.959 | 0 |
| direct-5 | lz4 | 0.887 | 0.919 | 0.930 | 32 |
| direct-5 | zstd | 0.958 | 0.974 | 0.938 | 32 |
| direct-8 | none | 0.901 | 0.904 | 0.933 | 0 |
| direct-8 | lz4 | 0.891 | 0.913 | 0.924 | 32 |
| direct-8 | zstd | 0.934 | 0.972 | 0.965 | 32 |
| palette-3 | none | 0.918 | 0.938 | 0.956 | 0 |
| palette-3 | lz4 | 0.843 | 0.830 | 0.894 | 48 |
| palette-3 | zstd | 0.951 | 0.955 | 0.983 | 48 |
| palette-5 | none | 0.921 | 0.914 | 0.944 | 0 |
| palette-5 | lz4 | 0.887 | 0.900 | 0.935 | 48 |
| palette-5 | zstd | 0.941 | 0.956 | 0.964 | 48 |
| local-two | none | 0.913 | 0.940 | 0.966 | 0 |
| local-two | lz4 | 0.879 | 0.891 | 0.918 | 48 |
| local-two | zstd | 0.989 | 0.967 | 0.966 | 48 |
| runs32 | none | 1.000 | 1.001 | 1.003 | 0 |
| runs32 | lz4 | 0.883 | 0.885 | 0.890 | 32 |
| runs32 | zstd | 0.997 | 0.973 | 1.006 | 32 |
| periodic | none | 1.002 | 1.013 | 0.971 | 0 |
| periodic | lz4 | 0.820 | 0.805 | 0.871 | 32 |
| periodic | zstd | 0.906 | 0.848 | 0.888 | 32 |
| span | none | 0.998 | 1.001 | 1.008 | 0 |
| span | lz4 | 0.829 | 0.862 | 0.862 | 32 |
| span | zstd | 0.918 | 0.924 | 0.939 | 32 |

Across the nine cases, median build ratios are 0.938 for none, 0.885 for LZ4 and 0.956 for ZSTD; update+flush ratios are 0.959, 0.894 and 0.964. These are medians of case ratios, not aggregate throughput measurements.

The largest unresolved codec-heavy cases improve only modestly: local-two ZSTD construction falls from 6.920 to 6.693 ms and update+flush from 5.447 to 5.260 ms. Runs32 ZSTD construction falls from 4.510 to 4.390 ms, while update+flush rises slightly from 3.559 to 3.580 ms (0.6%). Codec-free structured controls are approximately unchanged (largest reported construction increase 1.3% on periodic input). No significant new regression is established by those small differences. This change reduces Python overhead; it does not eliminate the expensive codec calls or close the large dense-Blosc gap.

## Exactness and scope

All uncompressed candidates are selected before compression begins. Strictly smaller replacements preserve stable ties: for example, an uncompressed palette wins against an equally sized compressed direct candidate. The ordinary winner size and structured/trim-aware codec pruning bound remain separate. Compression still runs direct packed, raw BITSHUFFLE, then optional palette packed; packed candidates use NOFILTER. Settings are level 5, typesize 1, one thread.

Every timed pair matched the initial encoded record, every initial cold chunk, and every post-update/flush cold chunk exactly. Logical contents, cache bounds and clear/reload checks passed. A separate untimed pass compared every construction candidate input and shuffle flag in order. Thus retained cold capacity is unchanged; this experiment does not measure transient peak allocation or RSS.

Thirteen focused tests additionally compare real-codec records/traces, post-mutation flush traces, payload lengths around 63/64/65 and 127/128/129, artificial compressed ties/pruning outcomes, and structured-versus-ordinary ties. Fake compression is used only for selection tests, never for timings or decoding. The prototype allocates no `_Chunk` candidates, candidate list or tuple snapshot; it still constructs required packed candidate payloads and performs the same codecs.

Data seed 8241 supplies random 3/5/8-bit and high-label palettes, plus existing local-two/runs32 seed 812, periodic and span controls. Trace/order seeds are 8242/8243. All datasets and array sizes are bounded. Updates XOR each written byte with 1, so each of 512 written values actually changes; those mutations can introduce new palette values or destroy structure.

```sh
python -m pytest tests/test_compressed_streaming_candidates.py
python -m benchmarks.compressed_streaming_candidates --repeats 11 --calls 100 --output streaming.json
```

The baseline Python is pinned; reproduction still requires the recorded native sources/binary. Production adoption should run normal typing, broad regression and failure-path checks separately.
