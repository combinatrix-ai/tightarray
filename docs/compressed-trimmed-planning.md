# Trim planning and ordering ablation

[This measured artifact](compressed-trimmed-planning-results.json) compares
pre-trim Python `d6b3746`, trim-before-RLE Python `c924947`, trim-after-RLE Python
`abba423`, and live trim-after-RLE native planning `f7d379f`. All use the same
current native extension. The [script](../benchmarks/compressed_trimmed_planning.py)
loads pinned classes into distinct modules, records their source hashes, and
guards live Python, all compressed native headers, binary and measured harness
sources. The JSON is copied unchanged from the run; prior artifacts remain intact.

Nine existing endpoint-study datasets each contain 1 MiB in 4096-byte chunks,
with a 64 KiB cache. Five paired repetitions shuffle nine methods: four variants
with none/ZSTD, plus dense ZSTD (level5, BITSHUFFLE, typesize1, one thread).
Dataset/order/access seeds and all raw samples are recorded. The earlier
[endpoint study](compressed-trimmed-endpoints.md) defines the patterns and traces.
All logical outputs and sampled cache bounds pass. Cold records are byte-identical
among the three trim variants initially and after the common 64 updates + flush.
Stored payload never exceeds pre-trim on these states. The nine-case smoke test
passes as well. The retained-graph metric includes native span references and
excludes shared runtime, native codec scratch, temporary allocations and allocator
arenas; it is not RSS.

## Construction and updates

Milliseconds, pre-trim / early Python / late Python / late native:

| Case | Codec | Construction | 64 updates + flush |
|---|---|---:|---:|
| half-random-half-zero | none | 2.310 / 2.207 / 2.558 / 2.238 | 0.552 / 0.872 / 0.937 / 0.815 |
| half-random-half-zero | zstd | 14.605 / 16.166 / 14.970 / 16.323 | 3.580 / 4.028 / 3.643 / 4.155 |
| half-zero-half-random | none | 2.171 / 2.448 / 2.992 / 2.313 | 0.604 / 0.903 / 0.938 / 0.862 |
| half-zero-half-random | zstd | 14.555 / 15.902 / 16.146 / 15.446 | 3.806 / 4.504 / 4.399 / 4.003 |
| central-island | none | 1.549 / 2.145 / 2.644 / 2.529 | 1.206 / 0.841 / 0.915 / 0.974 |
| central-island | zstd | 13.779 / 14.187 / 14.610 / 13.428 | 3.143 / 3.889 / 3.360 / 3.727 |
| random32 | none | 2.505 / 3.163 / 2.662 / 1.918 | 0.607 / 0.745 / 0.643 / 0.599 |
| random32 | zstd | 14.392 / 16.453 / 13.827 / 14.386 | 3.497 / 4.778 / 2.923 / 3.285 |
| half-with-edge-outlier | none | 2.085 / 2.814 / 2.258 / 2.174 | 0.569 / 0.664 / 0.615 / 0.584 |
| half-with-edge-outlier | zstd | 15.759 / 15.183 / 15.896 / 15.191 | 3.736 / 3.381 / 3.234 / 3.712 |
| rare-spikes | none | 1.383 / 2.313 / 1.672 / 1.605 | 1.023 / 1.426 / 1.110 / 0.976 |
| rare-spikes | zstd | 16.025 / 16.286 / 16.037 / 16.316 | 3.946 / 3.936 / 4.439 / 3.905 |
| uniform-chunks | none | 0.319 / 0.341 / 0.326 / 0.311 | 0.899 / 1.203 / 0.872 / 0.900 |
| uniform-chunks | zstd | 0.314 / 0.336 / 0.321 / 0.363 | 3.486 / 3.507 / 3.853 / 3.310 |
| nonmodal-long-edge | none | 1.657 / 2.733 / 1.906 / 1.616 | 0.792 / 0.852 / 0.786 / 0.705 |
| nonmodal-long-edge | zstd | 11.597 / 12.760 / 12.532 / 11.598 | 3.844 / 3.041 / 4.084 / 3.024 |
| distinct-edge-palette-adversary | none | 2.631 / 3.703 / 3.190 / 2.800 | 0.776 / 1.450 / 0.974 / 0.953 |
| distinct-edge-palette-adversary | zstd | 52.432 / 53.954 / 54.636 / 53.420 | 13.454 / 13.869 / 13.375 / 14.207 |

## Reads

Local/global milliseconds for 256 scalar reads. Local traces prewarm eight
chunks; global traces start cold. Early and native trim share the same access
representation and code, so short-phase timing differences do not establish
planner-caused read improvements. All operation samples, medium/block reads,
and cold/warm memory records remain available in the artifact.

| Case | Pre-trim none | Early none | Native none | Pre-trim ZSTD | Native ZSTD | Dense ZSTD |
|---|---:|---:|---:|---:|---:|---:|
| half-random-half-zero | 0.082 / 0.480 | 0.083 / 0.521 | 0.090 / 0.495 | 0.085 / 1.048 | 0.088 / 0.503 | 0.076 / 1.276 |
| half-zero-half-random | 0.087 / 0.476 | 0.086 / 0.505 | 0.082 / 0.705 | 0.080 / 1.081 | 0.085 / 0.524 | 0.080 / 1.325 |
| central-island | 0.088 / 2.241 | 0.082 / 0.442 | 0.085 / 0.418 | 0.082 / 1.120 | 0.087 / 0.436 | 0.076 / 1.464 |
| random32 | 0.086 / 0.500 | 0.086 / 0.514 | 0.082 / 0.583 | 0.084 / 0.488 | 0.087 / 0.489 | 0.077 / 1.431 |
| half-with-edge-outlier | 0.082 / 0.500 | 0.085 / 0.513 | 0.083 / 0.762 | 0.085 / 0.994 | 0.090 / 1.123 | 0.075 / 1.338 |
| rare-spikes | 0.085 / 0.877 | 0.089 / 0.541 | 0.091 / 0.536 | 0.086 / 0.537 | 0.087 / 0.664 | 0.073 / 1.379 |
| uniform-chunks | 0.082 / 0.062 | 0.064 / 0.063 | 0.062 / 0.061 | 0.064 / 0.064 | 0.063 / 0.064 | 0.081 / 1.305 |
| nonmodal-long-edge | 0.083 / 1.314 | 0.081 / 2.113 | 0.091 / 1.324 | 0.082 / 1.654 | 0.087 / 1.861 | 0.072 / 1.291 |
| distinct-edge-palette-adversary | 0.083 / 0.540 | 0.083 / 0.462 | 0.085 / 0.455 | 0.083 / 1.794 | 0.096 / 1.605 | 0.093 / 1.176 |

Reordering RLE ahead of trim planning recovers much of the overhead on rare
spikes and the nonmodal-long-edge case, where RLE already wins. Native planning
removes additional Python work. None construction on random data improves from
3.163 ms (early Python) to 1.918 ms (native), compared with 2.505 ms pre-trim in
this run. This is not evidence that unused planning intrinsically accelerates
the old representation: the small samples have visible timing variability.

Residual costs remain. The central island takes 2.529 ms to build versus
1.549 ms pre-trim; half-random updates take 0.815 versus 0.552 ms, inverse-half
updates 0.862 versus 0.604 ms, and palette-adversary updates 0.953 versus 0.776 ms.
Moving planning later also loses the early candidate's tighter RLE byte budget,
a possible explanation for the central-island construction tradeoff, not an
isolated causal measurement. ZSTD cost is dominated by codec trials; the native
planner does not consistently improve it (half-random 14.605 → 16.323 ms,
central island 13.779 → 13.428 ms, adversary 52.432 → 53.420 ms).

Capacity and structural access benefits persist because all trim variants encode
identical chunks. Central-island global none reads improve from 2.241 to 0.418 ms,
and ZSTD from 1.120 to 0.436 ms (dense ZSTD 1.464 ms). Half-random ZSTD global
reads improve from 1.048 to 0.503 ms. Local scalar reads remain around 0.08–0.09
ms, with dense ZSTD commonly around 0.07–0.08 ms. These are synthetic bounded
traces, not end-application throughput. The ablation supports reduced planning
cost without a storage-ratio tradeoff in the tested data; it does not establish
universal speedup or a universal nonregression theorem.

```sh
python -m benchmarks.compressed_trimmed_planning --output /tmp/planning.json
pytest -q tests/test_compressed_trimmed_planning.py
```
