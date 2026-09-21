# Fuse palette mapping with native packing

`_pack_palette` maps original bytes to palette indices in fixed 512-element blocks,
then uses the existing SIMD packed-byte kernels. Its inverse table and mapped
block occupy 1 KiB of stack scratch independent of input length. Blocks end on
word boundaries at every supported width; only the final block adds zero padding.
One output bytes allocation replaces the Python translation table, whole-input
translated bytes, and subsequent native output construction. Sorted unique palette,
width, missing values and size overflow are checked; invalid output is discarded.

Production uses the helper for both full palette candidates, palette-coded periodic
patterns, and palette-coded trimmed spans. Direct/no-palette paths are unchanged.
This retains record metadata, candidate ordering, strict size ties and codec inputs.

The [raw artifact](compressed-palette-pack-results.json.gz) is a lossless gzip copy
of the JSON result. It compares pinned `fa37aa2` Python with the injected helper
calls, both using the same new native extension. Existing `_pack_bytes` is unchanged;
only the candidate invokes the new `_pack_palette` method. All 144 configurations
use 15 randomized paired repeats of 128 operations. Workloads include high-label
palettes of 2/8/32/128 values; periods31/127/256 with tails; 509-element trimmed
spans with direct and palette widths; and direct controls. Phases are isolated
encode, one-chunk construction, and alternating actually changed 16-byte writes
with flush after every write. Exact final values/cold records and source guards
passed. Unit oracles additionally compare every compressor payload/filter in order.

Grouped median candidate/baseline ratios:

| Codec | Group | Encode | Construct | Changed write + flush |
|---|---|---:|---:|---:|
| none | palette | 0.917 | 0.921 | 0.939 |
| none | period | 0.828 | 0.834 | 0.913 |
| none | palette span | 0.923 | 0.947 | 0.929 |
| LZ4 | palette | 0.980 | 0.955 | 0.971 |
| LZ4 | period | 0.968 | 0.952 | 0.942 |
| LZ4 | palette span | 0.919 | 0.924 | 0.947 |
| ZSTD | palette | 0.986 | 0.992 | 0.977 |
| ZSTD | period | 0.950 | 0.977 | 0.973 |
| ZSTD | palette span | 0.974 | 0.966 | 0.966 |

No-codec direct control group medians range0.992–1.000. Codec controls vary too:
ZSTD direct changed-write ratios reach1.042 despite that path being unchanged.
Some modified cases also slightly regress: ZSTD palette construction reaches1.011,
and codec-free palette-span writes1.003. Thus these one-process microbenchmarks
support targeted gains, not universal codec or application throughput improvement.
The 128-label palette's no-codec encode ratio0.768 is a best case, not the headline
for every palette. Full raw samples retain these differences.

The native helper and production integration preserve fixed logical uint8 semantics
and existing cold bytes. Historical eager/packing oracle helpers remain available
for source-based tests. No new external dependency is introduced.

Validation: CPython 3.12 full suite 1391 passed; CPython 3.14 1064 passed and
93 optional-dependency skips. Official typing checks, strict mypy and Ruff passed.
An isolated ASan/UBSan build passed 141 tests; an isolated non-NEON build passed
273 tests. Both builds verified that the temporary extension was loaded rather
than the main one. Native and live-output tests are included in storage-pilots CI.

```sh
python -m benchmarks.compressed_palette_pack --repeats 15 --operations 128 --output results.json
python -m pytest tests/test_compressed_palette_pack.py tests/test_compressed_palette_pack_native.py
```
