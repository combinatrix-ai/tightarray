# Cached span mutation

The [benchmark](../benchmarks/compressed_span_updates.py) compares pinned
`5defad8` Python with the live cached-span mutation fast path `f9e2b93`, using
the same native extension. [Targeted raw results](compressed-span-updates-results.json)
and [nine-case matrix](compressed-span-updates-matrix.json) are preserved unchanged.
All measured-source and binary guards passed. Nine focused tests and lint passed.

One 4096-byte chunk has a 512-byte random 0..31 interior between zero edges. Its
5-bit hot span is 320 bytes, while full expansion needs 2560 bytes. Cache budgets
are 0, 512, and 65536 bytes. Each trial starts with the same scalar prewarm, performs
64 actual value-changing assignments within 0..31 and flushes. Inside/outside/mixed
traces use unique indices; mixed performs 32 inside then 32 outside writes. Both
none/ZSTD are compared; dense ZSTD appears with ZSTD only (level5, BITSHUFFLE,
typesize1, one thread). Random full chunks and periodic chunks are controls.
Five repetitions randomize method order; seeds are recorded. Construction and
full correctness checks are outside timing. Every output is verified before and
after clearing/reloading cold storage, including cache 0 and oversize paths.

## Targeted update medians

Milliseconds for 64 writes + flush:

| Budget | Codec | Region | Baseline | Live | Dense ZSTD |
|---:|---|---|---:|---:|---:|
| 0 | none | inside | 0.747500 | 0.828750 | — |
| 0 | none | outside | 0.947416 | 0.946667 | — |
| 0 | none | mixed | 0.852042 | 0.858084 | — |
| 0 | zstd | inside | 2.862583 | 3.005458 | 1.710542 |
| 0 | zstd | outside | 5.058000 | 5.204125 | 2.180250 |
| 0 | zstd | mixed | 3.803208 | 3.669292 | 1.738500 |
| 512 | none | inside | 0.817459 | 0.048791 | — |
| 512 | none | outside | 0.944959 | 0.952292 | — |
| 512 | none | mixed | 0.860375 | 0.489541 | — |
| 512 | zstd | inside | 2.923542 | 0.093208 | 1.586500 |
| 512 | zstd | outside | 5.134250 | 5.086500 | 2.205500 |
| 512 | zstd | mixed | 3.683708 | 2.104417 | 1.798500 |
| 65536 | none | inside | 0.047709 | 0.048959 | — |
| 65536 | none | outside | 0.044917 | 0.045542 | — |
| 65536 | none | mixed | 0.050000 | 0.049625 | — |
| 65536 | zstd | inside | 0.083209 | 0.087459 | 0.043125 |
| 65536 | zstd | outside | 0.128667 | 0.125875 | 0.052792 |
| 65536 | zstd | mixed | 0.107083 | 0.113042 | 0.047917 |

At 512-byte budget, inside writes improve 16.75× without a codec and 31.37× with
ZSTD. The old path expands beyond budget and repeatedly writes through; the new
path keeps the 320-byte span hot. Baseline counts 64 misses after prewarm, versus
live 64 hits and only the initial miss. Both cold payloads remain 326 bytes.
After flush the live none graph is 2403 bytes versus baseline 1862: the live cache
intentionally retains its hot data. Payload/cache/retained graph before, after
and reloaded are all captured; this graph estimate includes span references and
excludes native codec scratch/shared runtime/allocator arenas, and is not RSS.

This win requires fitting the compact hot span while expansion would exceed
budget. Cache0 has no corresponding gain. Outside writes still expand and behave
similarly. Mixed writes benefit for their first half, but live mixed ZSTD 2.104 ms
is still slower than dense 1.799 ms. At 65536 budget, inside none is 0.048959 versus
baseline 0.047709 ms and ZSTD 0.087459 versus0.083209 ms; dense ZSTD is 0.043125 ms.
The fast path is therefore a capacity-constrained locality win, not a general
mutation-throughput improvement.

Random controls have median live/base timing ratio 1.0018 over 18 configurations
(worst 1.036); periodic controls 1.0006 (worst 1.088). These small differences show
no consistent control-path speedup; raw repetitions retain the variability.

## Existing nine-case matrix

The unmodified `compressed_trimmed_integrated` harness was imported, its module
`BASELINE` set to `5defad8`, then `run(size=2**20,repeats=5)` called. This exact
invocation is recorded in the second artifact; the harness source was not edited.
All full-content, cache-budget and initial/postflush payload checks passed.
The usual 1 MiB/chunk4096/cache65536 matrix gives these update medians, baseline → live:

| Case | None | ZSTD |
|---|---:|---:|
| half-random-half-zero | 0.755 → 0.749 | 3.429 → 3.081 |
| half-zero-half-random | 0.827 → 0.777 | 3.441 → 3.096 |
| central-island | 0.845 → 0.800 | 3.221 → 3.046 |
| random32 | 0.533 → 0.529 | 2.640 → 2.623 |
| half-with-edge-outlier | 0.534 → 0.528 | 3.065 → 3.084 |
| rare-spikes | 0.951 → 0.987 | 3.637 → 3.455 |
| uniform-chunks | 0.857 → 0.863 | 2.985 → 2.918 |
| nonmodal-long-edge | 0.668 → 0.666 | 2.941 → 3.078 |
| distinct-edge-palette-adversary | 0.839 → 0.775 | 11.234 → 11.240 |

Broad gains are smaller, as expected at a larger cache budget. The sampled
nonmodal ZSTD update case regresses 2.941→3.078 ms (4.7%); it selects no trimmed
chunks. No widespread regression appears in this bounded run, but small timing
differences are not a guarantee. Cold byte identity was not required for the
targeted experiment because hot palette history may choose different physical
representations; logical contents are exact. All results are synthetic traces,
not end-application throughput measurements.

```sh
python -m benchmarks.compressed_span_updates --output /tmp/span-updates.json
pytest -q tests/test_compressed_span_updates.py
```
