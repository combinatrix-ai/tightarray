# Early versus late native trim planning

The [benchmark](../benchmarks/compressed_trimmed_ordering.py) subclasses the
pinned early-planning Python implementation `c924947` and overrides only
`_trim_plan` to call the native helper. It compares that early-native variant
against live late-native production (`f7d379f` implementation), pinned pre-trim
`d6b3746`, and dense ZSTD. The early variant includes an extra Python wrapper
call, whereas live production directly calls the helper; this is not a perfectly
symmetric instruction-level comparison. Production files were not modified.

The [unchanged run artifact](compressed-trimmed-ordering-results.json) records
all source/binary hashes and raw repetitions. Source guards passed across the
run. Nine datasets, 1 MiB each, 4096-byte chunks, 64 KiB cache, five shuffled
paired repetitions and seven methods use the existing
[endpoint protocol](compressed-trimmed-endpoints.md). Dense ZSTD is level5,
BITSHUFFLE, typesize1, one thread. Local scalar reads prewarm eight chunks;
global reads start cold. Scalar phases perform 256 reads; updates perform
64 assignments plus flush. Exact early/late cold records match before and after
updates, all logical contents/cache bounds pass, and stored payload does not
exceed pre-trim in tested states. The nine-case small smoke test and lint pass.

## Construction and updates

Milliseconds, pre-trim / early native / late native:

| Case | Codec | Construction | Updates + flush |
|---|---|---:|---:|
| half-random-half-zero | none | 1.900 / 1.747 / 2.506 | 0.794 / 0.764 / 0.842 |
| half-random-half-zero | zstd | 16.060 / 15.035 / 17.289 | 3.764 / 5.525 / 4.789 |
| half-zero-half-random | none | 2.118 / 2.002 / 2.911 | 0.615 / 1.575 / 1.718 |
| half-zero-half-random | zstd | 16.157 / 15.705 / 16.690 | 3.471 / 3.589 / 4.539 |
| central-island | none | 1.598 / 1.818 / 2.244 | 1.886 / 0.846 / 0.874 |
| central-island | zstd | 14.338 / 12.838 / 14.257 | 3.376 / 3.860 / 4.564 |
| random32 | none | 1.887 / 1.922 / 1.998 | 0.539 / 0.577 / 0.572 |
| random32 | zstd | 12.084 / 12.029 / 12.620 | 2.766 / 2.850 / 2.728 |
| half-with-edge-outlier | none | 1.884 / 1.916 / 2.015 | 0.583 / 0.596 / 0.612 |
| half-with-edge-outlier | zstd | 12.881 / 12.837 / 13.006 | 3.109 / 3.955 / 2.982 |
| rare-spikes | none | 1.369 / 1.815 / 1.662 | 0.951 / 1.021 / 0.982 |
| rare-spikes | zstd | 15.241 / 16.828 / 16.249 | 5.128 / 4.806 / 4.318 |
| uniform-chunks | none | 0.321 / 0.321 / 0.335 | 0.860 / 1.014 / 0.890 |
| uniform-chunks | zstd | 0.329 / 0.331 / 0.319 | 3.415 / 3.227 / 3.526 |
| nonmodal-long-edge | none | 1.739 / 1.753 / 1.688 | 0.655 / 0.954 / 0.726 |
| nonmodal-long-edge | zstd | 11.076 / 12.616 / 12.563 | 3.724 / 3.146 / 2.910 |
| distinct-edge-palette-adversary | none | 3.242 / 2.141 / 2.487 | 0.964 / 0.867 / 0.879 |
| distinct-edge-palette-adversary | zstd | 50.129 / 51.431 / 53.106 | 13.167 / 14.484 / 12.966 |

## Read medians

Local/global milliseconds; all medium, block-read and memory phases remain in
the artifact. Equivalent early/late stored representations use the same native
access implementation, so their short read-time differences are timing
variability rather than effects of planner ordering.

| Case | Pre-trim none | Early none | Late none | Pre-trim ZSTD | Early ZSTD | Late ZSTD | Dense ZSTD |
|---|---:|---:|---:|---:|---:|---:|---:|
| half-random-half-zero | 0.083 / 0.489 | 0.083 / 0.517 | 0.083 / 0.525 | 0.084 / 1.347 | 0.086 / 0.513 | 0.091 / 0.509 | 0.074 / 2.139 |
| half-zero-half-random | 0.091 / 0.507 | 0.083 / 0.595 | 0.084 / 0.610 | 0.083 / 1.018 | 0.088 / 0.537 | 0.087 / 0.511 | 0.073 / 1.487 |
| central-island | 0.084 / 2.164 | 0.082 / 0.402 | 0.083 / 0.411 | 0.084 / 1.122 | 0.091 / 0.404 | 0.085 / 0.398 | 0.073 / 1.305 |
| random32 | 0.085 / 0.464 | 0.082 / 0.486 | 0.080 / 0.460 | 0.089 / 0.473 | 0.081 / 0.484 | 0.086 / 0.467 | 0.072 / 1.263 |
| half-with-edge-outlier | 0.084 / 0.485 | 0.079 / 0.489 | 0.080 / 0.468 | 0.081 / 1.006 | 0.095 / 1.307 | 0.080 / 1.001 | 0.073 / 1.320 |
| rare-spikes | 0.094 / 0.536 | 0.082 / 0.536 | 0.080 / 0.528 | 0.083 / 0.542 | 0.084 / 0.539 | 0.082 / 0.551 | 0.075 / 1.929 |
| uniform-chunks | 0.063 / 0.062 | 0.062 / 0.061 | 0.066 / 0.062 | 0.063 / 0.062 | 0.061 / 0.060 | 0.059 / 0.062 | 0.073 / 1.250 |
| nonmodal-long-edge | 0.084 / 1.405 | 0.096 / 1.325 | 0.082 / 1.400 | 0.083 / 1.703 | 0.082 / 2.125 | 0.079 / 3.026 | 0.079 / 1.306 |
| distinct-edge-palette-adversary | 0.079 / 0.429 | 0.087 / 0.457 | 0.079 / 0.603 | 0.085 / 1.621 | 0.079 / 1.636 | 0.079 / 2.371 | 0.073 / 1.186 |

Early native planning improves construction on the four trim-beneficial cases:
half-random, inverse half, central island, and palette adversary. The island
none construction gap against pre-trim shrinks from 40% with late planning to
14% with early planning. Early planning also gives RLE a tighter size bound,
but this ablation does not separately isolate native recognition from RLE work.

Early planning pays for an unnecessary candidate on existing RLE winners: rare
spike none construction takes 1.815 versus late 1.662 ms, and nonmodal-long-edge
1.753 versus 1.688 ms. Random and edge-outlier construction are close between
orderings. Codec and update phases show mixed results and visible variability;
no unconditional speedup claim follows. The native planner is sufficiently cheap
that the earlier Python-only ordering result did not predict this tradeoff.

Storage is identical between orderings, including after updates. Retained graph
metrics include native span data/palette references; they exclude shared runtime,
codec workspace, temporary allocations and allocator arenas and are not RSS.
These are bounded synthetic traces, not application throughput or a proof of
all-input storage nonregression.

```sh
python -m benchmarks.compressed_trimmed_ordering --output /tmp/ordering.json
pytest -q tests/test_compressed_trimmed_ordering.py
```
