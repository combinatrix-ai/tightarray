# Materialize selected periods after RLE

This narrower lazy policy pins `ffe172a` and delays period slicing, translation, and packing only until the RLE encoder has returned. If RLE wins, the period is never materialized; otherwise an `elif period_selected` branch builds the same bytes record before the original structured/codec selection. Unlike the earlier fully lazy experiment, it does not maintain deferred state through codec selection. `period_record` remains bytes-or-None throughout.

The three paired policies are eager, after-RLE, and after-RLE plus the proven period-dominates-trim skip. Period-size calculations, RLE bounds, record types, strict ties, and codec candidate payload/filter/order remain unchanged. The trim skip is described in [the previous proof](compressed-lazy-period.md); the production correctness suite additionally tests its premise independently.

The same 96 pattern/palette/codec cases use 21 shuffled paired repeats of 128 isolated `_encode` calls. Construction and decoded validation are outside timing. Exact cold records, decoded contents, and every compressor input/filter/order match all three policies. A small no-Git correctness test includes partial tails. The artifact records pinned Python, live native/source, harness, and wrapper hashes.

Period allocation is actually avoided in 18 rows: 16 end with an RLE winner and two with a codec winner after RLE already eliminated the period. Other codec winners still pay period construction, by design. The old fully delayed opportunity flag is retained separately to avoid overstating saved work.

Ratios of summed case medians (less than one is faster; synthetic case-weighted aggregate, not application throughput):

| Codec | After RLE | After RLE + trim skip |
|---|---:|---:|
| none | 0.9613 | 0.9377 |
| lz4 | 0.9881 | 0.9810 |
| zstd | 0.9990 | 0.9943 |

This narrows the typical win to avoiding disposable RLE-losing periods: combined aggregate improves 6.2% without codecs, 1.9% LZ4, and 0.6% ZSTD. It is not uniformly faster. After-RLE's worst observed regression is 3.73% on random67-x16 palette/LZ4; combined's worst is 3.45% on ascending256-x2 without palette/ZSTD. No-codec worst regressions are 1.46% and 1.35%, respectively. These losses remain part of the result despite the larger repeat count.

All medians in microseconds:

| Case | Palette | Codec | Winner | Allocation avoided | Eager | After RLE | Combined |
|---|---|---|---|---|---:|---:|---:|
| random31-x2 | False | none | period | False | 1.538 | 1.539 | 1.480 |
| random31-x2 | False | lz4 | period | False | 3.305 | 3.314 | 3.252 |
| random31-x2 | False | zstd | period | False | 3.237 | 3.297 | 3.232 |
| random31-x2 | True | none | period | False | 1.574 | 1.587 | 1.513 |
| random31-x2 | True | lz4 | period | False | 3.368 | 3.374 | 3.299 |
| random31-x2 | True | zstd | period | False | 3.337 | 3.373 | 3.304 |
| random31-x16 | False | none | period | False | 2.697 | 2.712 | 2.641 |
| random31-x16 | False | lz4 | period | False | 17.190 | 17.557 | 17.271 |
| random31-x16 | False | zstd | period | False | 22.804 | 23.422 | 23.143 |
| random31-x16 | True | none | period | False | 2.655 | 2.648 | 2.590 |
| random31-x16 | True | lz4 | period | False | 17.743 | 17.526 | 17.206 |
| random31-x16 | True | zstd | period | False | 22.769 | 22.491 | 22.876 |
| high-two31-x2 | False | none | period | False | 1.610 | 1.598 | 1.544 |
| high-two31-x2 | False | lz4 | period | False | 8.829 | 8.676 | 8.645 |
| high-two31-x2 | False | zstd | period | False | 10.325 | 10.141 | 10.202 |
| high-two31-x2 | True | none | ordinary | False | 2.504 | 2.515 | 2.538 |
| high-two31-x2 | True | lz4 | ordinary | False | 2.483 | 2.509 | 2.493 |
| high-two31-x2 | True | zstd | ordinary | False | 2.529 | 2.521 | 2.522 |
| high-two31-x16 | False | none | period | False | 2.683 | 2.701 | 2.664 |
| high-two31-x16 | False | lz4 | period | False | 17.420 | 17.293 | 17.028 |
| high-two31-x16 | False | zstd | period | False | 21.098 | 21.399 | 21.525 |
| high-two31-x16 | True | none | period | False | 3.039 | 3.036 | 2.993 |
| high-two31-x16 | True | lz4 | period | False | 3.058 | 3.118 | 3.017 |
| high-two31-x16 | True | zstd | period | False | 3.146 | 3.115 | 3.069 |
| random67-x2 | False | none | period | False | 1.738 | 1.733 | 1.670 |
| random67-x2 | False | lz4 | period | False | 14.069 | 13.948 | 14.093 |
| random67-x2 | False | zstd | period | False | 17.561 | 17.465 | 17.012 |
| random67-x2 | True | none | period | False | 1.762 | 1.787 | 1.714 |
| random67-x2 | True | lz4 | period | False | 14.309 | 14.229 | 14.422 |
| random67-x2 | True | zstd | period | False | 17.564 | 17.753 | 17.604 |
| random67-x16 | False | none | period | False | 2.879 | 2.902 | 2.829 |
| random67-x16 | False | lz4 | period | False | 18.414 | 18.523 | 17.807 |
| random67-x16 | False | zstd | period | False | 31.057 | 31.105 | 31.093 |
| random67-x16 | True | none | period | False | 2.804 | 2.829 | 2.745 |
| random67-x16 | True | lz4 | period | False | 18.072 | 18.746 | 18.455 |
| random67-x16 | True | zstd | period | False | 31.211 | 31.983 | 30.525 |
| high-eight127-x2 | False | none | period | False | 2.053 | 2.055 | 1.980 |
| high-eight127-x2 | False | lz4 | period | False | 16.387 | 16.095 | 16.369 |
| high-eight127-x2 | False | zstd | codec | False | 24.338 | 24.768 | 23.938 |
| high-eight127-x2 | True | none | period | False | 2.581 | 2.602 | 2.523 |
| high-eight127-x2 | True | lz4 | period | False | 24.435 | 23.455 | 23.808 |
| high-eight127-x2 | True | zstd | period | False | 33.423 | 33.692 | 32.702 |
| high-eight127-x16 | False | none | period | False | 3.031 | 3.017 | 2.955 |
| high-eight127-x16 | False | lz4 | period | False | 18.902 | 19.063 | 18.575 |
| high-eight127-x16 | False | zstd | codec | False | 30.874 | 30.317 | 31.031 |
| high-eight127-x16 | True | none | period | False | 3.539 | 3.579 | 3.491 |
| high-eight127-x16 | True | lz4 | period | False | 28.046 | 28.852 | 28.090 |
| high-eight127-x16 | True | zstd | period | False | 48.659 | 48.540 | 48.859 |
| long-runs127-x2 | False | none | runs | True | 2.233 | 1.729 | 1.708 |
| long-runs127-x2 | False | lz4 | runs | True | 2.251 | 1.752 | 1.688 |
| long-runs127-x2 | False | zstd | runs | True | 2.266 | 1.760 | 1.690 |
| long-runs127-x2 | True | none | runs | True | 2.747 | 1.885 | 1.824 |
| long-runs127-x2 | True | lz4 | runs | True | 2.808 | 1.899 | 1.856 |
| long-runs127-x2 | True | zstd | runs | True | 2.767 | 1.915 | 1.859 |
| long-runs127-x16 | False | none | runs | True | 3.971 | 3.454 | 3.358 |
| long-runs127-x16 | False | lz4 | runs | True | 20.437 | 19.448 | 18.935 |
| long-runs127-x16 | False | zstd | runs | True | 24.873 | 24.057 | 24.370 |
| long-runs127-x16 | True | none | period | False | 3.823 | 3.815 | 3.736 |
| long-runs127-x16 | True | lz4 | period | False | 28.184 | 28.041 | 27.512 |
| long-runs127-x16 | True | zstd | period | False | 35.174 | 36.003 | 36.176 |
| spike251-x2 | False | none | runs | True | 3.364 | 2.850 | 2.766 |
| spike251-x2 | False | lz4 | runs | True | 3.367 | 2.835 | 2.780 |
| spike251-x2 | False | zstd | runs | True | 3.414 | 2.871 | 2.825 |
| spike251-x2 | True | none | runs | True | 3.980 | 3.035 | 2.940 |
| spike251-x2 | True | lz4 | runs | True | 3.896 | 2.973 | 2.915 |
| spike251-x2 | True | zstd | runs | True | 3.931 | 2.987 | 2.908 |
| spike251-x16 | False | none | runs | True | 5.521 | 5.044 | 4.805 |
| spike251-x16 | False | lz4 | codec | True | 23.324 | 22.268 | 21.747 |
| spike251-x16 | False | zstd | codec | True | 28.429 | 28.318 | 27.801 |
| spike251-x16 | True | none | period | False | 5.158 | 5.132 | 5.033 |
| spike251-x16 | True | lz4 | period | False | 31.878 | 31.272 | 31.225 |
| spike251-x16 | True | zstd | period | False | 41.160 | 40.337 | 40.832 |
| ascending256-x2 | False | none | period | False | 2.934 | 2.948 | 2.775 |
| ascending256-x2 | False | lz4 | codec | False | 17.703 | 17.957 | 18.049 |
| ascending256-x2 | False | zstd | codec | False | 22.923 | 23.718 | 23.713 |
| ascending256-x2 | True | none | period | False | 2.897 | 2.902 | 2.728 |
| ascending256-x2 | True | lz4 | codec | False | 17.903 | 18.274 | 18.002 |
| ascending256-x2 | True | zstd | codec | False | 23.338 | 22.800 | 23.412 |
| ascending256-x16 | False | none | period | False | 3.623 | 3.579 | 3.465 |
| ascending256-x16 | False | lz4 | period | False | 22.667 | 22.273 | 22.588 |
| ascending256-x16 | False | zstd | codec | False | 27.798 | 28.573 | 28.345 |
| ascending256-x16 | True | none | period | False | 3.579 | 3.591 | 3.459 |
| ascending256-x16 | True | lz4 | period | False | 22.577 | 22.568 | 22.119 |
| ascending256-x16 | True | zstd | codec | False | 27.911 | 27.732 | 27.369 |
| nonperiodic32 | False | none | ordinary | False | 6.059 | 6.075 | 6.140 |
| nonperiodic32 | False | lz4 | ordinary | False | 21.858 | 21.408 | 22.359 |
| nonperiodic32 | False | zstd | ordinary | False | 46.902 | 47.498 | 47.023 |
| nonperiodic32 | True | none | ordinary | False | 6.029 | 5.995 | 5.999 |
| nonperiodic32 | True | lz4 | ordinary | False | 22.122 | 22.163 | 22.476 |
| nonperiodic32 | True | zstd | ordinary | False | 46.746 | 46.922 | 46.796 |
| uniform | False | none | uniform | False | 0.830 | 0.830 | 0.831 |
| uniform | False | lz4 | uniform | False | 0.852 | 0.852 | 0.850 |
| uniform | False | zstd | uniform | False | 0.857 | 0.853 | 0.855 |
| uniform | True | none | uniform | False | 0.839 | 0.840 | 0.843 |
| uniform | True | lz4 | uniform | False | 0.850 | 0.848 | 0.853 |
| uniform | True | zstd | uniform | False | 0.845 | 0.846 | 0.844 |

[Raw 21-repeat results](compressed-period-after-rle-results.json). Reproduce with `python -m benchmarks.compressed_period_after_rle --output docs/compressed-period-after-rle-results.json`. This experiment alone changes no production source.

## Adoption and post-measurement harness maintenance

The combined after-RLE/trim-skip policy was selected for production integration. Following the measurement, the benchmark gained an AST-guided `eager_source` normalizer to reverse the formatted adopted branch for no-history correctness tests; both old fully-lazy and new after-RLE tests use it. It preserves unrelated source, tolerates comments/formatting, and has an AST round-trip regression check. This test maintenance was not part of timing. The original measured wrapper is preserved at commit-time provenance by its SHA256 `4008703dbb0c74a353c9b0f44f51cccb7c63b609ac11751146e48e64e9cf7fb0`; a temporary exact copy was saved before editing. Historical raw samples and recorded hashes are unchanged, so the current wrapper hash intentionally differs.
