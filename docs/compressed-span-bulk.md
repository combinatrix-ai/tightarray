# Cached partial span bulk writes

The [paired benchmark](../benchmarks/compressed_span_bulk.py) compares pinned
`6a3ffb2` Python against live `57bd581` bulk-write behavior, using the same native
extension. [Raw results](compressed-span-bulk-results.json) are unchanged from
the guarded run at checkout `857f064`. All measured source/header/binary hashes
matched before/after. Twelve focused smoke tests and all 72 measured configurations
passed exact logical values, flush/clear/reload, and cache-budget checks.

Four fixtures put a 512-byte random interior in a 4096-byte zero-filled chunk:
direct 3-bit, palette 3-bit, direct 5-bit and palette 5-bit. Their initial hot payloads
are 192/200/320/352 bytes respectively. Each trial has the same scalar prewarm,
then 32 partial writes of 16 bytes and a final flush. Every assigned byte differs
from its value at that moment: 512 real changes per trial, verified before timing.
Inside writes stay within the interior; outside writes stay in the zero prefix;
mixed writes perform 16 inside then 16 outside. Cache budgets are 0, 512, 65536;
codecs none/ZSTD; five repetitions randomize baseline/live/dense order.

The dense ZSTD comparator decodes once per touched chunk and byte-slice-assigns
once, then caches or encodes once. It does not emulate bulk operations with a
scalar loop. It uses the existing byte-bounded dirty LRU helper, ZSTD level5,
BITSHUFFLE, typesize1 and one thread. Inputs are prevalidated fixture bytes; the
helper does not implement all of the public tightarray write validation, so this
is not a fully symmetric API-overhead comparison. Equal budgets bound payload,
not RSS. Graph metrics include metadata/buffers but exclude shared runtime,
native codec workspace, temporary scratch and allocator arenas.

## Affected paths and controls

Inside/cache512 none writes improve 6.69–7.30× and ZSTD 14.36–18.32×. Live ZSTD
costs 0.094–0.159 ms versus dense 0.763–0.856 ms, because dense 4096-byte hot chunks
cannot fit while the compact spans can. Baseline adaptive expands past budget
and repeatedly writes through; live retains the 192–352-byte span. For none,
after-flush owned graph is 2147/2163/2403/2467 bytes live versus 1734/1742/1862/1894
baseline: the live graph intentionally includes retained hot buffers. Cold
payload remains 198/206/326/358 bytes, respectively. Full before/after/reloaded
payload/cache/owned metrics are in the artifact.

Inside/cache65536 also improves, by 2.69–3.43× none and 1.99–2.32× ZSTD: this
bulk path avoids repeated full-span materialization even when expansion could
fit. Dense cached ZSTD is still faster, around 0.040–0.044 ms versus live 0.092–0.151
ms. Mixed/cache512 gains 1.53–1.93× against baseline but still loses to dense ZSTD.
Outside writes still expand. Cache0 live/base medians across configurations have
median 1.012 and range 0.929–1.100; outside/cache512 median 0.993 and range 0.921–1.056.
These controls show no consistent gain and include small sampled regressions.
This is a targeted locality/capacity optimization, not a universal advantage over
dense bulk mutation or an application E2E result.

## All 72 configurations

Milliseconds for 32 writes + flush; real changed values=512 in every row. Dense
ZSTD is included only with the matching ZSTD adaptive configuration. Construction
and correctness verification are excluded from timing.

| Layout | Budget | Codec | Region | Baseline | Live | Dense ZSTD |
|---|---:|---|---|---:|---:|---:|
| direct-3bit | 0 | none | inside | 0.403042 | 0.404000 | — |
| direct-3bit | 0 | none | outside | 0.427250 | 0.432584 | — |
| direct-3bit | 0 | none | mixed | 0.411917 | 0.414708 | — |
| direct-3bit | 0 | zstd | inside | 1.442833 | 1.456875 | 0.775708 |
| direct-3bit | 0 | zstd | outside | 2.166542 | 2.012334 | 0.925709 |
| direct-3bit | 0 | zstd | mixed | 1.651583 | 1.816125 | 0.840709 |
| direct-3bit | 512 | none | inside | 0.410750 | 0.056791 | — |
| direct-3bit | 512 | none | outside | 0.434542 | 0.431459 | — |
| direct-3bit | 512 | none | mixed | 0.417500 | 0.239084 | — |
| direct-3bit | 512 | zstd | inside | 1.412542 | 0.093667 | 0.763208 |
| direct-3bit | 512 | zstd | outside | 2.220333 | 2.075042 | 0.991000 |
| direct-3bit | 512 | zstd | mixed | 1.666958 | 0.935625 | 0.811000 |
| direct-3bit | 65536 | none | inside | 0.151625 | 0.056208 | — |
| direct-3bit | 65536 | none | outside | 0.150667 | 0.151041 | — |
| direct-3bit | 65536 | none | mixed | 0.159875 | 0.109875 | — |
| direct-3bit | 65536 | zstd | inside | 0.192833 | 0.091709 | 0.040834 |
| direct-3bit | 65536 | zstd | outside | 0.209792 | 0.210750 | 0.055417 |
| direct-3bit | 65536 | zstd | mixed | 0.204583 | 0.166917 | 0.045750 |
| palette-3bit | 0 | none | inside | 0.525917 | 0.526583 | — |
| palette-3bit | 0 | none | outside | 0.635709 | 0.642917 | — |
| palette-3bit | 0 | none | mixed | 0.574583 | 0.582667 | — |
| palette-3bit | 0 | zstd | inside | 2.360208 | 2.390167 | 0.800792 |
| palette-3bit | 0 | zstd | outside | 3.332166 | 3.386292 | 1.014750 |
| palette-3bit | 0 | zstd | mixed | 2.566958 | 2.665959 | 0.841792 |
| palette-3bit | 512 | none | inside | 0.563834 | 0.084333 | — |
| palette-3bit | 512 | none | outside | 0.635667 | 0.638000 | — |
| palette-3bit | 512 | none | mixed | 0.586625 | 0.350291 | — |
| palette-3bit | 512 | zstd | inside | 2.497875 | 0.136375 | 0.796416 |
| palette-3bit | 512 | zstd | outside | 3.343250 | 3.529959 | 1.023208 |
| palette-3bit | 512 | zstd | mixed | 2.599167 | 1.693500 | 0.823417 |
| palette-3bit | 65536 | none | inside | 0.247750 | 0.072333 | — |
| palette-3bit | 65536 | none | outside | 0.251625 | 0.259375 | — |
| palette-3bit | 65536 | none | mixed | 0.252750 | 0.169083 | — |
| palette-3bit | 65536 | zstd | inside | 0.308708 | 0.133083 | 0.040250 |
| palette-3bit | 65536 | zstd | outside | 0.348792 | 0.355500 | 0.049333 |
| palette-3bit | 65536 | zstd | mixed | 0.333125 | 0.244791 | 0.046375 |
| direct-5bit | 0 | none | inside | 0.409833 | 0.408584 | — |
| direct-5bit | 0 | none | outside | 0.490833 | 0.493208 | — |
| direct-5bit | 0 | none | mixed | 0.444334 | 0.448208 | — |
| direct-5bit | 0 | zstd | inside | 1.524833 | 1.566375 | 0.846792 |
| direct-5bit | 0 | zstd | outside | 2.186167 | 2.212834 | 1.004041 |
| direct-5bit | 0 | zstd | mixed | 2.090000 | 2.125584 | 0.909125 |
| direct-5bit | 512 | none | inside | 0.418083 | 0.057292 | — |
| direct-5bit | 512 | none | outside | 0.501292 | 0.497709 | — |
| direct-5bit | 512 | none | mixed | 0.454500 | 0.268792 | — |
| direct-5bit | 512 | zstd | inside | 1.611875 | 0.112250 | 0.856083 |
| direct-5bit | 512 | zstd | outside | 2.502625 | 2.304333 | 1.040708 |
| direct-5bit | 512 | zstd | mixed | 1.851958 | 1.129375 | 0.893625 |
| direct-5bit | 65536 | none | inside | 0.161292 | 0.059916 | — |
| direct-5bit | 65536 | none | outside | 0.160375 | 0.157208 | — |
| direct-5bit | 65536 | none | mixed | 0.156750 | 0.109250 | — |
| direct-5bit | 65536 | zstd | inside | 0.199708 | 0.100542 | 0.043541 |
| direct-5bit | 65536 | zstd | outside | 0.228000 | 0.230250 | 0.051500 |
| direct-5bit | 65536 | zstd | mixed | 0.207291 | 0.166125 | 0.046458 |
| palette-5bit | 0 | none | inside | 0.628792 | 0.602459 | — |
| palette-5bit | 0 | none | outside | 0.672916 | 0.682292 | — |
| palette-5bit | 0 | none | mixed | 0.624291 | 0.617042 | — |
| palette-5bit | 0 | zstd | inside | 2.629958 | 2.731583 | 0.883958 |
| palette-5bit | 0 | zstd | outside | 3.613000 | 3.674125 | 1.018375 |
| palette-5bit | 0 | zstd | mixed | 2.924292 | 2.720042 | 0.885917 |
| palette-5bit | 512 | none | inside | 0.591583 | 0.088041 | — |
| palette-5bit | 512 | none | outside | 0.669083 | 0.664875 | — |
| palette-5bit | 512 | none | mixed | 0.625833 | 0.371667 | — |
| palette-5bit | 512 | zstd | inside | 2.510167 | 0.158959 | 0.843208 |
| palette-5bit | 512 | zstd | outside | 3.740000 | 3.567834 | 1.066292 |
| palette-5bit | 512 | zstd | mixed | 3.001625 | 1.552875 | 0.895833 |
| palette-5bit | 65536 | none | inside | 0.283042 | 0.087167 | — |
| palette-5bit | 65536 | none | outside | 0.278625 | 0.281583 | — |
| palette-5bit | 65536 | none | mixed | 0.279125 | 0.184459 | — |
| palette-5bit | 65536 | zstd | inside | 0.343500 | 0.151125 | 0.041541 |
| palette-5bit | 65536 | zstd | outside | 0.396750 | 0.399583 | 0.052000 |
| palette-5bit | 65536 | zstd | mixed | 0.371125 | 0.271875 | 0.047541 |

```sh
python -m benchmarks.compressed_span_bulk --output /tmp/span-bulk.json
python -m pytest -q tests/test_compressed_span_bulk_benchmark.py
```
