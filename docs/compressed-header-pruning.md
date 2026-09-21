# Exact minimum-header pruning

The [paired benchmark](../benchmarks/compressed_header_pruning.py) compares
pinned `d90c7dd` Python against live `440f9a0`, using the same native extension.
[Raw results](compressed-header-pruning-results.json) are copied unchanged.
All measured source/header/binary guards pass. Sixteen cases (the fourteen codec
policy cases plus direct/high-valued two-state periods), three codecs and five
shuffled paired repetitions use 1 MiB, chunks4096 and cache65536. Cases use seeds
812/681, ordering724, traces914. There are 256 scalar reads per access phase and
64 updates plus flush; updates may include unchanged values. Construction and
mutation compression calls are counted in a separate untimed instrumented pass,
so counters do not affect operation timings.

The sixteen-case small smoke test and lint pass. Exact cold records match before
and after the common updates/flush for every case and codec. All logical contents
and cache bounds pass. None is a control; dense codecs are not part of this
isolation experiment. Retained graph fields include native span references and
exclude shared runtime, codec scratch and allocator arenas; they are not RSS.

## Why the bound is safe

Installed Blosc2 4.13.1 / C-Blosc2 3.3.4 exposes `MIN_HEADER_LENGTH=16`, not 32.
The installed primary header `blosc2/include/blosc2.h` labels 16 as the minimum
Blosc1 header and 32 as the extended Blosc2 header. `blosc2_ext.pyx` exports that
minimum and rejects compressed buffers shorter than it. Special zero/NaN/uninit
chunks return the extended-header size, and repeated-value chunks add typesize;
none invalidate the conservative 16-byte lower bound.

A compressed candidate retains the two-byte tightarray descriptor and its own
palette. If an attainable complete record is strictly smaller than
`2 + MIN_HEADER_LENGTH + len(candidate.palette)`, that candidate cannot win.
Equality is deliberately not pruned: tie order must remain intact. The existing
payload<64 guard remains. Whole-record and candidate-specific checks can use the
best already available representation, including earlier compressed candidates.
This is a format lower bound, not an entropy/incompressibility heuristic.

Earlier untimed static counts predicted 768/768 eliminations for high-two-period31,
69/747 for rare spikes and no other initial eliminations among the fourteen
cases. Sixty rare-spike equality cases remained eligible. The measured initial
call counts below confirm that prediction. Additional mutation-state wins arise
when edits to uniform chunks leave a very small RLE record.

## Call counts and complete operation timings

Each cell is baseline → pruned. Times are medians in milliseconds. Call counts
refer to the separate pass's construction / updates-flush phases.

| Case | Codec | Calls build/update | Build ms | Update ms | Global scalar ms |
|---|---|---|---:|---:|---:|
| random8 | lz4 | 512/104 → 512/104 | 6.292 → 6.443 | 1.440 → 1.408 | 0.426 → 0.433 |
| random8 | zstd | 512/104 → 512/104 | 10.847 → 10.386 | 2.321 → 2.227 | 0.482 → 0.449 |
| random32 | lz4 | 512/110 → 512/110 | 6.251 → 6.296 | 1.563 → 1.517 | 0.467 → 0.453 |
| random32 | zstd | 512/110 → 512/110 | 11.622 → 11.407 | 2.672 → 2.903 | 0.472 → 0.480 |
| local-two | lz4 | 768/156 → 768/156 | 10.900 → 11.295 | 2.939 → 3.237 | 0.286 → 0.344 |
| local-two | zstd | 768/156 → 768/156 | 111.030 → 111.331 | 24.293 → 24.704 | 0.284 → 0.269 |
| uniform-chunks | lz4 | 0/153 → 0/19 | 0.307 → 0.307 | 2.376 → 1.198 | 0.058 → 0.056 |
| uniform-chunks | zstd | 0/153 → 0/19 | 0.313 → 0.313 | 2.905 → 1.218 | 0.056 → 0.057 |
| runs32 | lz4 | 512/110 → 512/110 | 7.636 → 7.963 | 2.009 → 2.102 | 0.819 → 0.855 |
| runs32 | zstd | 512/110 → 512/110 | 75.942 → 74.747 | 16.794 → 16.763 | 0.816 → 0.810 |
| rare-spikes | lz4 | 747/156 → 678/146 | 8.701 → 8.425 | 2.484 → 2.670 | 0.528 → 0.539 |
| rare-spikes | zstd | 747/156 → 678/146 | 13.554 → 12.537 | 3.934 → 3.765 | 0.519 → 0.535 |
| high-two-period31 | lz4 | 768/90 → 0/90 | 8.229 → 1.150 | 1.252 → 1.299 | 0.230 → 0.227 |
| high-two-period31 | zstd | 768/90 → 0/90 | 10.263 → 1.116 | 1.746 → 1.860 | 0.231 → 0.245 |
| threebit-period67 | lz4 | 512/100 → 512/100 | 5.738 → 5.838 | 1.510 → 1.502 | 0.231 → 0.245 |
| threebit-period67 | zstd | 512/100 → 512/100 | 7.798 → 7.646 | 1.908 → 2.144 | 0.231 → 0.227 |
| cycle31 | lz4 | 512/108 → 512/108 | 5.851 → 6.019 | 1.837 → 1.835 | 0.259 → 0.230 |
| cycle31 | zstd | 512/108 → 512/108 | 8.616 → 8.642 | 2.423 → 2.487 | 0.230 → 0.231 |
| high-cycle32 | lz4 | 768/159 → 768/159 | 8.919 → 8.790 | 2.511 → 2.441 | 0.236 → 0.240 |
| high-cycle32 | zstd | 768/159 → 768/159 | 10.135 → 10.593 | 3.246 → 3.002 | 0.233 → 0.229 |
| half-random-half-zero | lz4 | 512/106 → 512/106 | 6.899 → 6.921 | 1.766 → 1.746 | 0.482 → 0.517 |
| half-random-half-zero | zstd | 512/106 → 512/106 | 12.763 → 12.654 | 3.169 → 3.173 | 0.518 → 0.463 |
| changing-high-alphabet | lz4 | 768/165 → 768/165 | 10.271 → 10.253 | 3.102 → 3.159 | 0.679 → 0.639 |
| changing-high-alphabet | zstd | 768/165 → 768/165 | 47.589 → 47.720 | 12.336 → 12.383 | 0.732 → 0.670 |
| skew8 | lz4 | 512/104 → 512/104 | 7.732 → 7.735 | 1.944 → 1.956 | 0.923 → 0.850 |
| skew8 | zstd | 512/104 → 512/104 | 24.866 → 25.274 | 5.539 → 5.708 | 1.821 → 1.659 |
| periodic-sparse-high | lz4 | 768/180 → 768/180 | 11.934 → 11.951 | 3.934 → 3.721 | 1.111 → 1.224 |
| periodic-sparse-high | zstd | 768/180 → 768/180 | 99.992 → 100.958 | 24.810 → 24.770 | 1.374 → 1.411 |
| two-period-direct | lz4 | 512/64 → 0/64 | 5.555 → 1.005 | 1.005 → 0.983 | 0.226 → 0.239 |
| two-period-direct | zstd | 512/64 → 0/64 | 6.250 → 1.024 | 1.053 → 1.088 | 0.227 → 0.228 |
| two-period-high | lz4 | 768/96 → 0/96 | 8.385 → 1.092 | 1.332 → 1.345 | 0.237 → 0.234 |
| two-period-high | zstd | 768/96 → 0/96 | 9.397 → 1.156 | 1.602 → 1.635 | 0.239 → 0.239 |

High-two-period31 construction improves 7.16× with LZ4 and 9.20× with ZSTD by
eliminating all 768 calls. Direct/high two-state periods likewise eliminate all
construction codec calls. Their changed chunks generally lose exact periodicity,
so update call counts do not decrease. Uniform-chunk updates instead drop 153→19
calls and improve 1.98× LZ4 /2.39× ZSTD. Rare-spike improvement is smaller.

No other construction call counts change, including the expensive local-two,
runs32, skew8 and changing-high-alphabet cases. This optimization therefore does
not solve those broader codec-selection costs. Updates on unaffected paths have
mixed small regressions/improvements: for example local-two LZ4 goes 2.939→3.237
ms, and threebit-period67 ZSTD 1.908→2.144 ms, with unchanged counts and contents.
All individual repetitions are retained, rather than treating every small median
difference as causal. The none-control median live/base ratios across cases are
1.000 for build, 0.985 for updates, 1.026 for global reads; ranges are 0.911–1.089,
0.904–1.109 and 0.827–1.116, respectively. Global access representation is identical,
so no read-speed improvement is attributed to pruning.

This run confirms substantial targeted savings without changing stored bytes on
the tested inputs. It is bounded evidence, not universal performance or application
throughput. The safety argument rests on the documented minimum record length
and strict comparison, not on these benchmark outcomes.

```sh
python -m benchmarks.compressed_header_pruning --output /tmp/header-pruning.json
pytest -q tests/test_compressed_header_pruning.py
```
