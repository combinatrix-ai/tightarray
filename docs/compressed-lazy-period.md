# Lazy periodic-record materialization

This isolated prototype loads pinned `faf98fd` Python source with the current native extension and compares four policies: eager baseline, lazy periodic-record materialization, skipping the trim planner when a periodic candidate has been selected, and both changes together. Production is not edited. The timing covers `_encode` itself, not full construction or application E2E.

Lazy selection retains the chosen period length, bits, palette, and exact record size. It defers slicing/translating/packing the period until that candidate actually wins. Materialization is inlined at the return sites to avoid a new helper call on winners. RLE bounds, codec candidate inputs/order, and strict comparisons remain unchanged. The independent trim-skip policy tests an additional structural argument without conflating its contribution with lazy allocation.

## Why a selected period rules out a smaller trimmed span

Let the discovered exact period have length p, with input length at least 2p, as required by the native recognizer. For any proposed default value, the nonuniform first period contains a nondefault symbol at some position i<p. The same symbol occurs at i+p. A span retaining every nondefault occurrence therefore has length at least p+1 and contains a full period, hence every alphabet value. It cannot remove a color or reduce direct/palette bit width. Word rounding is monotone with length. Both candidates consider the same direct/palette alternatives, while the trim descriptor has eight bytes versus the period's three. Thus a trimmed candidate cannot beat the selected optimal period representation. If RLE already beats that period, trim cannot beat RLE either. Partial final periods do not change this argument because the first two complete periods exist.

## Oracle and timing

Sixteen pattern/repetition cases, palette enabled/disabled, and none/LZ4/ZSTD produce 96 rows. Each row checks exact final records, decoded values, and every compressor input byte string/filter in order across all four policies. A separate no-codec test includes partial tails. Timing uses seven shuffled paired repeats of 64 encodes per policy; raw samples and before/after source hashes are retained.

Selected periods lose in 26 rows: 16 to RLE and 10 to codecs. No trim winners occur, consistent with the argument above. Examples include long two-color runs, periodic sparse spikes, ascending byte cycles, and high-label eight-state periods compressed by ZSTD.

Ratio of summed per-case median encode time to eager baseline (case-weighted synthetic aggregate, less than one is faster):

| Codec | Lazy only | Skip trim only | Combined |
|---|---:|---:|---:|
| none | 0.957 | 0.975 | 0.931 |
| lz4 | 0.975 | 0.995 | 0.988 |
| zstd | 0.987 | 1.003 | 0.991 |

All-case medians in microseconds:

| Case | Palette | Codec | Winner | Period discarded | Eager | Lazy | Skip trim | Combined |
|---|---|---|---|---|---:|---:|---:|---:|
| random31-x2 | False | none | period | False | 1.621 | 1.641 | 1.569 | 1.593 |
| random31-x2 | False | lz4 | period | False | 3.725 | 3.617 | 3.611 | 3.568 |
| random31-x2 | False | zstd | period | False | 3.695 | 3.676 | 3.630 | 3.610 |
| random31-x2 | True | none | period | False | 1.679 | 1.665 | 1.617 | 1.588 |
| random31-x2 | True | lz4 | period | False | 3.943 | 4.124 | 3.800 | 3.854 |
| random31-x2 | True | zstd | period | False | 3.786 | 3.783 | 3.700 | 3.684 |
| random31-x16 | False | none | period | False | 2.688 | 2.692 | 2.602 | 2.674 |
| random31-x16 | False | lz4 | period | False | 18.802 | 17.876 | 17.598 | 17.802 |
| random31-x16 | False | zstd | period | False | 24.675 | 23.556 | 23.660 | 23.842 |
| random31-x16 | True | none | period | False | 2.750 | 2.747 | 2.682 | 2.698 |
| random31-x16 | True | lz4 | period | False | 18.038 | 17.916 | 19.347 | 19.134 |
| random31-x16 | True | zstd | period | False | 23.898 | 22.945 | 24.771 | 22.987 |
| high-two31-x2 | False | none | period | False | 1.714 | 1.650 | 1.529 | 1.565 |
| high-two31-x2 | False | lz4 | period | False | 8.652 | 8.614 | 8.648 | 8.653 |
| high-two31-x2 | False | zstd | period | False | 10.088 | 10.026 | 9.953 | 10.157 |
| high-two31-x2 | True | none | ordinary | False | 2.553 | 2.504 | 2.566 | 2.518 |
| high-two31-x2 | True | lz4 | ordinary | False | 2.492 | 2.512 | 2.499 | 2.516 |
| high-two31-x2 | True | zstd | ordinary | False | 2.527 | 2.674 | 2.498 | 2.535 |
| high-two31-x16 | False | none | period | False | 2.712 | 2.729 | 2.648 | 2.671 |
| high-two31-x16 | False | lz4 | period | False | 16.750 | 17.207 | 16.917 | 16.559 |
| high-two31-x16 | False | zstd | period | False | 21.067 | 21.098 | 20.824 | 21.347 |
| high-two31-x16 | True | none | period | False | 3.057 | 3.053 | 2.997 | 2.987 |
| high-two31-x16 | True | lz4 | period | False | 3.053 | 3.048 | 2.984 | 2.986 |
| high-two31-x16 | True | zstd | period | False | 3.036 | 3.044 | 2.962 | 3.023 |
| random67-x2 | False | none | period | False | 1.745 | 1.732 | 1.663 | 1.655 |
| random67-x2 | False | lz4 | period | False | 14.424 | 14.305 | 13.924 | 15.403 |
| random67-x2 | False | zstd | period | False | 17.273 | 17.312 | 17.680 | 17.147 |
| random67-x2 | True | none | period | False | 1.737 | 1.729 | 1.674 | 1.650 |
| random67-x2 | True | lz4 | period | False | 14.393 | 14.925 | 14.397 | 14.404 |
| random67-x2 | True | zstd | period | False | 17.439 | 17.436 | 17.398 | 17.394 |
| random67-x16 | False | none | period | False | 2.822 | 2.845 | 2.745 | 2.747 |
| random67-x16 | False | lz4 | period | False | 19.680 | 17.936 | 18.444 | 18.502 |
| random67-x16 | False | zstd | period | False | 30.771 | 31.070 | 30.902 | 31.246 |
| random67-x16 | True | none | period | False | 2.833 | 2.831 | 2.775 | 2.756 |
| random67-x16 | True | lz4 | period | False | 18.473 | 18.794 | 18.508 | 18.607 |
| random67-x16 | True | zstd | period | False | 31.574 | 31.331 | 30.984 | 34.135 |
| high-eight127-x2 | False | none | period | False | 2.027 | 2.018 | 1.960 | 1.945 |
| high-eight127-x2 | False | lz4 | period | False | 16.223 | 15.866 | 16.292 | 16.792 |
| high-eight127-x2 | False | zstd | codec | True | 23.991 | 23.657 | 23.862 | 22.986 |
| high-eight127-x2 | True | none | period | False | 2.591 | 2.581 | 2.521 | 2.528 |
| high-eight127-x2 | True | lz4 | period | False | 23.356 | 23.611 | 24.583 | 23.331 |
| high-eight127-x2 | True | zstd | period | False | 33.495 | 31.786 | 35.354 | 32.394 |
| high-eight127-x16 | False | none | period | False | 3.016 | 3.025 | 2.954 | 2.955 |
| high-eight127-x16 | False | lz4 | period | False | 18.782 | 18.893 | 19.881 | 20.258 |
| high-eight127-x16 | False | zstd | codec | True | 30.962 | 31.484 | 30.302 | 30.613 |
| high-eight127-x16 | True | none | period | False | 3.646 | 3.648 | 3.580 | 3.596 |
| high-eight127-x16 | True | lz4 | period | False | 30.231 | 29.039 | 28.012 | 28.210 |
| high-eight127-x16 | True | zstd | period | False | 47.661 | 48.010 | 49.354 | 50.927 |
| long-runs127-x2 | False | none | runs | True | 2.364 | 1.817 | 2.324 | 1.725 |
| long-runs127-x2 | False | lz4 | runs | True | 2.301 | 1.798 | 2.218 | 1.739 |
| long-runs127-x2 | False | zstd | runs | True | 2.324 | 1.836 | 2.231 | 1.710 |
| long-runs127-x2 | True | none | runs | True | 2.779 | 1.921 | 2.717 | 1.868 |
| long-runs127-x2 | True | lz4 | runs | True | 3.203 | 2.049 | 3.094 | 1.959 |
| long-runs127-x2 | True | zstd | runs | True | 2.911 | 2.020 | 2.836 | 1.939 |
| long-runs127-x16 | False | none | runs | True | 3.957 | 3.456 | 3.850 | 3.355 |
| long-runs127-x16 | False | lz4 | runs | True | 22.516 | 19.397 | 21.270 | 21.237 |
| long-runs127-x16 | False | zstd | runs | True | 25.098 | 24.537 | 25.040 | 24.330 |
| long-runs127-x16 | True | none | period | False | 3.747 | 3.732 | 3.633 | 3.633 |
| long-runs127-x16 | True | lz4 | period | False | 27.569 | 27.660 | 27.078 | 29.064 |
| long-runs127-x16 | True | zstd | period | False | 36.064 | 35.890 | 36.524 | 35.825 |
| spike251-x2 | False | none | runs | True | 3.367 | 2.840 | 3.466 | 2.773 |
| spike251-x2 | False | lz4 | runs | True | 3.456 | 2.842 | 3.299 | 2.784 |
| spike251-x2 | False | zstd | runs | True | 3.383 | 2.859 | 3.318 | 2.830 |
| spike251-x2 | True | none | runs | True | 3.842 | 2.938 | 3.788 | 2.877 |
| spike251-x2 | True | lz4 | runs | True | 3.919 | 2.978 | 3.961 | 2.927 |
| spike251-x2 | True | zstd | runs | True | 3.908 | 2.971 | 3.831 | 2.969 |
| spike251-x16 | False | none | runs | True | 5.516 | 4.984 | 5.346 | 4.822 |
| spike251-x16 | False | lz4 | codec | True | 22.589 | 22.011 | 22.072 | 22.130 |
| spike251-x16 | False | zstd | codec | True | 28.934 | 27.863 | 28.308 | 27.869 |
| spike251-x16 | True | none | period | False | 5.225 | 5.142 | 5.049 | 4.945 |
| spike251-x16 | True | lz4 | period | False | 30.908 | 30.889 | 30.957 | 30.663 |
| spike251-x16 | True | zstd | period | False | 40.175 | 40.171 | 39.797 | 42.662 |
| ascending256-x2 | False | none | period | False | 2.938 | 2.891 | 2.742 | 2.757 |
| ascending256-x2 | False | lz4 | codec | True | 17.971 | 17.622 | 18.215 | 17.352 |
| ascending256-x2 | False | zstd | codec | True | 23.500 | 22.199 | 24.554 | 22.347 |
| ascending256-x2 | True | none | period | False | 2.974 | 2.943 | 2.799 | 2.762 |
| ascending256-x2 | True | lz4 | codec | True | 17.675 | 17.148 | 17.869 | 17.043 |
| ascending256-x2 | True | zstd | codec | True | 23.335 | 22.400 | 23.915 | 23.071 |
| ascending256-x16 | False | none | period | False | 3.618 | 3.599 | 3.449 | 3.431 |
| ascending256-x16 | False | lz4 | period | False | 21.990 | 22.329 | 23.265 | 22.656 |
| ascending256-x16 | False | zstd | codec | True | 28.167 | 27.075 | 27.747 | 25.770 |
| ascending256-x16 | True | none | period | False | 3.726 | 3.690 | 3.419 | 3.480 |
| ascending256-x16 | True | lz4 | period | False | 23.040 | 22.066 | 22.077 | 21.833 |
| ascending256-x16 | True | zstd | codec | True | 28.518 | 27.716 | 27.445 | 26.456 |
| nonperiodic32 | False | none | ordinary | False | 6.260 | 6.294 | 6.428 | 6.257 |
| nonperiodic32 | False | lz4 | ordinary | False | 21.979 | 21.881 | 22.149 | 22.934 |
| nonperiodic32 | False | zstd | ordinary | False | 45.602 | 47.159 | 45.443 | 46.245 |
| nonperiodic32 | True | none | ordinary | False | 6.303 | 6.301 | 6.332 | 6.312 |
| nonperiodic32 | True | lz4 | ordinary | False | 22.786 | 22.307 | 23.422 | 22.374 |
| nonperiodic32 | True | zstd | ordinary | False | 46.258 | 48.204 | 47.025 | 46.217 |
| uniform | False | none | uniform | False | 0.842 | 0.833 | 0.838 | 0.831 |
| uniform | False | lz4 | uniform | False | 0.865 | 0.865 | 0.864 | 0.867 |
| uniform | False | zstd | uniform | False | 0.864 | 0.865 | 0.864 | 0.867 |
| uniform | True | none | uniform | False | 0.865 | 0.840 | 0.857 | 0.859 |
| uniform | True | lz4 | uniform | False | 0.829 | 0.831 | 0.829 | 0.830 |
| uniform | True | zstd | uniform | False | 0.829 | 0.829 | 0.828 | 0.828 |

The strongest improvements occur when short RLE records make the eagerly packed period disposable. For palette-enabled long-runs127 repeated twice, no-codec encoding falls from 2.779 to 1.921 µs with lazy allocation and 1.868 µs combined. LZ4 falls from 3.203 to 2.050/1.959 µs respectively. The skipped work includes period translation and packed allocation.

Gains are not universal. Lazy-only's worst observed regression is 5.8% on high-two31-x2 with palette/ZSTD, where the ordinary representation wins and no periodic candidate is selected. Combined's worst is 8.1% on random67-x16 palette/ZSTD with a periodic winner (31.574 to 34.135 µs). Codec-dominated rows are variable; the modest aggregate codec gains and observed losses should be retained rather than claiming every encoder is faster. The trim-skip-only ZSTD aggregate is slightly slower (1.003×).

[Raw results](compressed-lazy-period-results.json) preserve all 96 rows. Reproduce with `python -m benchmarks.compressed_lazy_period --output docs/compressed-lazy-period-results.json`; `--oracle-only` performs a small no-codec check without timing. The prototype does not change the cold format, and correctness here is measured over the stated finite matrix, with the trim dominance argument given separately.
