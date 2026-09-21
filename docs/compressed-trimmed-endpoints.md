# Endpoint trimmed-span comparison

A value can omit a nonempty leading or trailing run only if it equals an
endpoint. `_byte_edge_spans` therefore supplies at most two candidates without
scanning a histogram. The benchmark-only policy compares both candidates by
exact eight-byte-header + palette + word-rounded packed size, then allocates
only the best candidate if it beats the existing encoded chunk. It calls the
exhaustive baseline encoder once. The existing modal prototype and production
behavior remain unchanged.

The [script](../benchmarks/compressed_trimmed_endpoints.py) compares baseline,
native modal, native endpoint, and dense LZ4/ZSTD storage. The
[raw artifact](compressed-trimmed-endpoints-results.json) is the unchanged run
output. Baseline Python source is pinned to `eff5443`, combined with the native
extension built after `9d603ec`; source and binary hashes were unchanged across
the run. Guards explicitly include `_compressed_trim.h` and this script.
The original seven cases use the prior [protocol](compressed-trimmed-policy.md):
1 MiB input, 4096-byte chunks, 64 KiB hot cache, 256 reads per scalar phase,
64 updates + flush, dense codecs level5/BITSHUFFLE/typesize1/one thread. Five
paired repetitions shuffle eight methods. Two added cases use seed725:
nonmodal long edge with a mostly-zero interior, and distinct edges where omitting
the shorter high-valued edge shrinks the palette from five to four colors.

Five correctness tests cover round trips, slices, mutations and boundary access,
plus independent enumeration of all 256 possible defaults over 100 small random
patterns with palette enabled/disabled. The endpoint result matches the smallest
exact uncompressed-span candidate or the original encoding. This is a property
of this specific format, not of compressed spans or all compression methods.
The shorter-edge adversary verifies that choosing solely by run length is wrong.
All full benchmark operation results were checked against the logical bytes.

Construction medians, milliseconds, baseline / modal / endpoint:

| Case | None | ZSTD |
|---|---:|---:|
| Random half, zero half | 2.522 / 6.119 / 4.326 | 14.515 / 19.866 / 18.013 |
| Zero half, random half | 2.082 / 5.035 / 3.602 | 14.019 / 16.552 / 15.672 |
| Central random island | 1.558 / 4.475 / 2.602 | 12.445 / 15.859 / 13.633 |
| Random 32 labels | 1.801 / 2.601 / 2.988 | 12.457 / 13.197 / 13.474 |
| Half with edge outlier | 1.878 / 3.762 / 2.823 | 13.411 / 15.168 / 14.873 |
| Rare spikes | 1.305 / 4.257 / 1.663 | 14.242 / 17.688 / 14.695 |
| Uniform chunks | 0.324 / 0.341 / 0.324 | 0.399 / 0.340 / 0.332 |
| Nonmodal long edge | 1.472 / 4.268 / 2.974 | 11.483 / 15.106 / 12.259 |
| Distinct-edge palette adversary | 2.618 / 6.482 / 5.073 | 48.138 / 53.990 / 54.143 |

For the original seven cases, modal and endpoint retained graph sizes are equal.
The distinct-edge adversary improves none storage from baseline406789 to
modal334597 to endpoint243205 bytes. Existing ZSTD already uses212719 bytes,
so neither trimmed candidate wins there (dense ZSTD212181). The nonmodal-long-edge
case gains nothing because the original RLE representation is already smaller:
259097 bytes without a codec and100847 with ZSTD. Thus a semantically valid extra
candidate does not necessarily improve the chosen storage.

On central-island data, endpoint global reads take0.459 ms versus baseline2.073
without a codec; updates + flush cost0.965 versus0.819 ms. Half-random endpoint
updates cost1.189 versus0.678 ms. The distinct-edge adversary updates cost1.601
versus0.741 ms. Full local/global/block-read and update samples are retained in
the artifact, including noisy short timings; equal access code between modal
and endpoint candidates should not be interpreted as different read algorithms.

Endpoint recognition improves construction relative to modal recognition on
most cases, but still adds cost over the baseline. Random data gets worse:
the cheap recognizer can trigger two full interior palette scans. The one-bit
minimum-size guard rejects only clearly impossible candidates; it cannot infer
palette or bit-width stability. Duplicate palette work, exhaustive original
encoding and Python structural hot access remain. No default adoption follows
from this prototype. A future fused candidate builder needs separate tests and
measurements rather than extrapolation from recognition speed alone.

Retained sizes use the common deduplicated reachable object graph, including
custom hot slot fields and native Array buffers; they exclude shared runtime
state, native codec workspaces, temporary allocations and allocator arenas.
They are not RSS. These are bounded synthetic experiments, not application E2E.

```sh
python -m benchmarks.compressed_trimmed_endpoints --output /tmp/endpoints.json
pytest -q tests/test_compressed_trimmed_endpoints.py
```
