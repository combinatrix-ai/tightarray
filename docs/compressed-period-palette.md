# Periodic pattern palette minimization

The [benchmark](../benchmarks/compressed_period_palette.py) compares pinned
`4857c2a` Python with live `fc46ea3` periodic-pattern palette selection, using the
same native extension. The [raw result](compressed-period-palette-results.json)
is preserved unchanged. Source hashes cover Python, harness, shared graph walker,
all compressed native headers and binary; all guards passed.

The four exact patterns and repeat counts from the production unit tests are
each repeated as 256 independent chunks. Thus high32/period32 and high-two/period2
use 1 MiB, high-two/period31 uses 1,015,808 bytes, and the ten-byte chunk fixture
uses 2560 bytes. Low-period31, random32 and a late-mismatch pattern provide
controls. Every case uses cache 65536 and five shuffled paired repetitions for
none/LZ4/ZSTD. The standard harness checks all logical outputs and post-edit
flush/reload, plus cache bounds and nonincreasing initial/postflush payload.
Records intentionally differ. A seven-case smoke test passes, as does the
historical header-prune smoke test after pinning its optimized Python class.

The change compares direct and indexed physical periodic-pattern size including
palette bytes and word rounding. A palette useful for the full logical chunk
may cost more than a direct tiny pattern. Conversely the 31-byte two-label pattern
still benefits from its two-byte palette, which must remain available.

## Capacity

Values are baseline → live; none-codec graph values shown. The payload changes
are identical across all three codecs. Warm cache is after prewarming eight
chunks and performing 256 local reads. Graph figures include metadata/native
buffers and exclude shared runtime, codec scratch and allocator arenas; not RSS.

| Case | Chunk bytes | Logical bytes | Cold payload | Cold owned graph | Warm cache payload | Warm owned graph |
|---|---:|---:|---:|---:|---:|---:|
| high32-period32 | 4096 | 1048576 | 14592 → 8448 | 27005 → 20869 | 448 → 256 | 29657 → 23098 |
| high-two-period2 | 4096 | 1048576 | 2816 → 2304 | 15109 → 14597 | 80 → 64 | 17393 → 16634 |
| high-two-period31 | 3968 | 1015808 | 2816 → 2816 | 15109 → 15109 | 80 → 80 | 17393 → 17393 |
| tiny-high-period2 | 10 | 2560 | 2560 → 2304 | 14853 → 14597 | 128 → 64 | 16926 → 16634 |
| low-period31-control | 3968 | 1015808 | 6400 → 6400 | 18693 → 18693 | 192 → 192 | 20858 → 20858 |
| random32-control | 4096 | 1048576 | 655360 → 655360 | 667653 → 667653 | 20480 → 20480 | 690106 → 690106 |
| late-mismatch-control | 4096 | 1048576 | 665088 → 665088 | 677381 → 677381 | 20736 → 20736 | 700385 → 700385 |

The 32-label high-valued pattern saves 42.1% of cold payload and 22.7% of retained
graph size. Its warm pattern payload shrinks 448→256 bytes. The two-byte high
pattern saves 18.2% of cold payload; the ten-byte logical chunk saves 10% and now
qualifies for periodic storage. The 31-byte high-valued pattern keeps its palette
and unchanged size. All three controls retain unchanged capacity.

## Operation medians

Milliseconds, baseline → live. Each scalar phase contains 256 reads, and edits
contain 64 assignments plus flush; values drawn from the alphabet can include
no-ops. Local reads prewarm eight chunks, global reads start cold. The artifact
also includes medium and 64-byte block reads and all post-update storage figures.

| Case | Codec | Build | Local reads | Global reads | Edits + flush |
|---|---|---:|---:|---:|---:|
| high32-period32 | none | 1.252 → 1.026 | 0.075 → 0.080 | 0.249 → 0.227 | 1.000 → 1.034 |
| high32-period32 | lz4 | 8.668 → 7.034 | 0.081 → 0.076 | 0.239 → 0.233 | 2.373 → 2.372 |
| high32-period32 | zstd | 10.239 → 8.135 | 0.078 → 0.076 | 0.243 → 0.234 | 3.303 → 3.036 |
| high-two-period2 | none | 1.068 → 0.996 | 0.075 → 0.074 | 0.230 → 0.228 | 0.528 → 0.522 |
| high-two-period2 | lz4 | 1.102 → 0.982 | 0.075 → 0.079 | 0.229 → 0.226 | 1.325 → 1.423 |
| high-two-period2 | zstd | 1.077 → 0.990 | 0.077 → 0.088 | 0.284 → 0.227 | 1.828 → 1.727 |
| high-two-period31 | none | 1.124 → 1.097 | 0.086 → 0.074 | 0.233 → 0.227 | 0.553 → 0.546 |
| high-two-period31 | lz4 | 1.088 → 1.113 | 0.074 → 0.075 | 0.236 → 0.242 | 1.396 → 1.476 |
| high-two-period31 | zstd | 1.096 → 1.102 | 0.078 → 0.073 | 0.237 → 0.229 | 1.767 → 1.783 |
| tiny-high-period2 | none | 0.493 → 0.437 | 0.077 → 0.073 | 0.221 → 0.230 | 0.185 → 0.172 |
| tiny-high-period2 | lz4 | 0.495 → 0.439 | 0.079 → 0.073 | 0.221 → 0.237 | 0.212 → 0.174 |
| tiny-high-period2 | zstd | 0.475 → 0.440 | 0.072 → 0.076 | 0.221 → 0.223 | 0.205 → 0.172 |
| low-period31-control | none | 1.066 → 0.967 | 0.079 → 0.076 | 0.236 → 0.231 | 0.709 → 0.721 |
| low-period31-control | lz4 | 5.777 → 5.914 | 0.075 → 0.076 | 0.229 → 0.232 | 1.773 → 1.677 |
| low-period31-control | zstd | 8.550 → 8.499 | 0.078 → 0.076 | 0.231 → 0.231 | 2.310 → 2.600 |
| random32-control | none | 1.840 → 1.798 | 0.077 → 0.076 | 0.452 → 0.488 | 0.536 → 0.549 |
| random32-control | lz4 | 6.157 → 6.166 | 0.078 → 0.079 | 0.473 → 0.459 | 1.493 → 1.619 |
| random32-control | zstd | 11.298 → 11.368 | 0.077 → 0.077 | 0.596 → 0.494 | 2.607 → 2.792 |
| late-mismatch-control | none | 2.904 → 2.937 | 0.080 → 0.075 | 0.557 → 0.597 | 0.895 → 0.864 |
| late-mismatch-control | lz4 | 9.310 → 9.559 | 0.075 → 0.077 | 0.926 → 0.914 | 2.547 → 2.813 |
| late-mismatch-control | zstd | 11.017 → 11.194 | 0.077 → 0.076 | 0.952 → 0.975 | 3.452 → 3.239 |

Construction improves on the direct-pattern wins, including high32 ZSTD
10.239→8.135 ms and none 1.252→1.026 ms. Controls generally show similar construction
cost. Read/edit medians are mixed and short-phase variability is visible: random
ZSTD edits 2.607→2.792 ms, low-period31 ZSTD 2.310→2.600 ms, while high32 ZSTD edits
3.303→3.036 ms. These measurements support the exact capacity reduction and some
construction savings, not a universal mutation/read-speed improvement. Synthetic
pattern results are not application E2E results.

```sh
python -m benchmarks.compressed_period_palette --output /tmp/period-palette.json
pytest -q tests/test_compressed_period_palette.py
```
