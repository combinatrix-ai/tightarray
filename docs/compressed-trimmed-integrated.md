# Integrated trimmed-span comparison

The production endpoint planner and native `_SpanHot` are compared with the
pre-trim Python implementation pinned to `d6b3746`. Both use the same current
native extension. Production sources were frozen during the run and subsequently
committed as `c924947`; hashes, rather than that later commit label, identify the
measured files. [Raw results](compressed-trimmed-integrated-results.json) are
copied unchanged. The [script](../benchmarks/compressed_trimmed_integrated.py)
guards all `_compressed*.h` files, native binary, Python implementation and
relevant benchmark sources. Historical prototype artifacts remain unchanged.

Nine cases each contain 1 MiB, partitioned into4096-byte chunks with a64 KiB
cache budget. Five paired repetitions shuffle six methods: baseline and live
none/ZSTD, plus dense LZ4/ZSTD. The [endpoint protocol](compressed-trimmed-endpoints.md)
provides dataset definitions, seeds and traces. Dense codecs use level5,
BITSHUFFLE, typesize1, one thread. Local reads prewarm eight chunks; global reads
start cold. Scalar phases perform256 reads; updates perform64 assignments plus
flush. All logical outputs, sampled cache bounds and initial/postflush stored
payload sizes were checked. Live payload never exceeded baseline in these runs.
Sixteen focused tests passed, including a small nine-case integrated run and
explicit native span reference/dedup accounting.

Cold and warm retained sizes use the same deduplicated reachable graph for all
methods. The walker now follows native `_SpanHot.data` and `.palette`, which
have no Python `__dict__`; they are no longer omitted from warm accounting.
These values include metadata and referenced buffers, exclude shared runtime
state, native codec scratch, temporary allocations and allocator arenas, and
are not RSS. Warm below means after the prewarmed local scalar phase. The full
artifact also preserves medium/global/block-read and post-update graphs.

## Capacity

Retained graph bytes, baseline → live. Trims count selected cold chunks.

| Case | Codec | Cold graph | Warm graph | Trims |
|---|---|---:|---:|---:|
| half-random-half-zero | none | 667773 → 341629 | 690226 → 353906 | 256 |
| half-random-half-zero | zstd | 355444 → 341621 | 377897 → 353898 | 256 |
| half-zero-half-random | none | 667701 → 341557 | 690154 → 353834 | 256 |
| half-zero-half-random | zstd | 355357 → 341533 | 377810 → 353810 | 256 |
| central-island | none | 521749 → 177669 | 544202 → 184826 | 256 |
| central-island | zstd | 192753 → 177653 | 215206 → 184810 | 256 |
| random32 | none | 667653 → 667653 | 690106 → 690106 | 0 |
| random32 | zstd | 667637 → 667637 | 690090 → 690090 | 0 |
| half-with-edge-outlier | none | 667653 → 667653 | 690106 → 690106 | 0 |
| half-with-edge-outlier | zstd | 355572 → 355572 | 378025 → 378025 | 0 |
| rare-spikes | none | 19140 → 19140 | 32169 → 32169 | 0 |
| rare-spikes | zstd | 19124 → 19124 | 32153 → 32153 | 0 |
| uniform-chunks | none | 7813 → 7813 | 7813 → 7813 | 0 |
| uniform-chunks | zstd | 7797 → 7797 | 7797 → 7797 | 0 |
| nonmodal-long-edge | none | 259097 → 259097 | 281550 → 281550 | 0 |
| nonmodal-long-edge | zstd | 100847 → 100847 | 123300 → 123300 | 0 |
| distinct-edge-palette-adversary | none | 406789 → 243205 | 421321 → 252410 | 256 |
| distinct-edge-palette-adversary | zstd | 212719 → 212719 | 247460 → 247460 | 0 |

## Complete operation medians

Milliseconds, baseline → live. Short phases and some construction samples show
visible variability; the artifact preserves all repetitions rather than hiding
outliers. Identical representations/access paths in no-trim cases do not justify
attributing their read-time differences to this change.

| Case | Codec | Build | Local reads | Global reads | Updates + flush |
|---|---|---:|---:|---:|---:|
| half-random-half-zero | none | 1.918 → 2.267 | 0.080 → 0.080 | 0.624 → 0.527 | 0.878 → 0.836 |
| half-random-half-zero | zstd | 15.695 → 17.195 | 0.092 → 0.084 | 1.001 → 1.022 | 3.454 → 3.783 |
| half-zero-half-random | none | 2.804 → 4.575 | 0.089 → 0.083 | 0.536 → 0.655 | 0.670 → 1.086 |
| half-zero-half-random | zstd | 18.587 → 21.204 | 0.080 → 0.088 | 0.992 → 0.555 | 3.422 → 5.736 |
| central-island | none | 1.543 → 2.027 | 0.082 → 0.088 | 3.907 → 0.436 | 0.994 → 0.842 |
| central-island | zstd | 17.846 → 15.877 | 0.082 → 0.086 | 1.092 → 0.402 | 3.305 → 5.512 |
| random32 | none | 1.879 → 2.315 | 0.084 → 0.082 | 0.469 → 0.515 | 0.680 → 0.689 |
| random32 | zstd | 15.529 → 15.315 | 0.085 → 0.081 | 0.464 → 0.473 | 2.848 → 4.245 |
| half-with-edge-outlier | none | 2.176 → 2.330 | 0.085 → 0.088 | 0.486 → 0.501 | 0.572 → 0.650 |
| half-with-edge-outlier | zstd | 17.387 → 17.482 | 0.096 → 0.080 | 1.082 → 1.610 | 4.034 → 4.137 |
| rare-spikes | none | 1.417 → 2.624 | 0.085 → 0.085 | 0.687 → 0.554 | 1.189 → 1.471 |
| rare-spikes | zstd | 17.978 → 22.576 | 0.085 → 0.085 | 2.077 → 0.552 | 4.497 → 4.261 |
| uniform-chunks | none | 0.327 → 0.333 | 0.064 → 0.067 | 0.092 → 0.075 | 1.061 → 1.160 |
| uniform-chunks | zstd | 0.328 → 0.330 | 0.064 → 0.064 | 0.069 → 0.063 | 3.437 → 5.244 |
| nonmodal-long-edge | none | 1.443 → 3.820 | 0.086 → 0.084 | 1.335 → 3.200 | 1.141 → 0.886 |
| nonmodal-long-edge | zstd | 14.838 → 15.855 | 0.083 → 0.084 | 2.630 → 3.374 | 4.672 → 3.558 |
| distinct-edge-palette-adversary | none | 3.960 → 3.397 | 0.086 → 0.088 | 0.475 → 0.506 | 1.050 → 1.019 |
| distinct-edge-palette-adversary | zstd | 57.493 → 64.465 | 0.084 → 0.084 | 3.257 → 2.318 | 15.915 → 21.324 |

## Interpretation

The integrated representation retains the capacity wins: half-random chunks use
48.8% less cold graph memory without a codec and3.9% less with ZSTD; the central
island saves65.9% and7.8%. Native span access keeps local scalar cost near the
baseline and central-island global reads improve substantially in this trace.

Construction and updates still regress in several cases, including no-trim
random, rare-spike and nonmodal-long-edge inputs. No-trim cold storage is equal,
so these workloads pay planning cost without gaining capacity. The edge/palette
adversary saves40.2% against none but is still larger than dense LZ4
(243205 versus235431 bytes), and existing ZSTD beats both. Its live ZSTD
construction takes64.465 ms versus dense ZSTD6.492 ms; exhaustive multi-candidate
encoding remains costly even though the retained result is comparable.

The current change demonstrates memory and some access benefits, not universal
speed improvement. Native candidate planning may reduce Python scans/temporary
objects, but requires its own measurements; recognition-only prototypes already
showed that eliminating a histogram does not eliminate duplicate palette work.
These are bounded synthetic traces, not application E2E or RSS measurements.
Stored-payload nonregression was verified for these exact initial and updated
states, not claimed as an exhaustive proof for all possible inputs.

```sh
python -m benchmarks.compressed_trimmed_integrated --output /tmp/integrated.json
pytest -q tests/test_compressed_trimmed_integrated.py
```
