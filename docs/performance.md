# Measured performance

Measured on Apple M1 Pro, ARM64 macOS, 2026-09-13.

CPython `3.14.7`, NumPy `2.5.3`; clang `-O3 -mcpu=apple-m1`.
Medians of repeated adaptive timing batches. Each result is verified before timing.

## Measurement boundaries

- The machine was not isolated: existing services were left running; recorded load averages are in the JSON metadata. No affinity or cold-cache control was used.
- Inputs are seeded uniform small integers; these are workload-specific results, not universal speedups.
- `equal` measures native `.equals()` for tightarray and `np.array_equal` for NumPy; elementwise comparison and NumPy dispatch are measured separately in the NumPy API report.
- `get` measures a single Python-level call; `random-get-sum` reads 256 prepared indices through Python and normalizes scalar values.
- `iterate-sum` deliberately iterates in Python; it is not NumPy's native `sum` reduction.
- `find` uses an eight-symbol repeated-maximum needle. An early match may end the scan. Do not compare search times across widths as equal amounts of work.
- Python-list and NumPy `find` include conversion to bytes; bytes/str use their native search. tightarray includes needle construction.
- `gather` uses prepared native `intp` buffers for NumPy and tightarray; `gather-list` passes the same Python list to both. Older JSON used different input formats and is not a matched gather baseline.
- Nested construction uses the same Python rows for every implementation; NumPy ragged includes flattening and offsets construction.
- Retained size counts owned buffers, object headers, shared objects once, and allocations kept alive by views. It is not RSS.
- Additional peak bytes are measured separately with tracemalloc: PyMem and NumPy-tracked allocations are included; untracked system allocations are excluded.
- View creation and copying are separate methods. An array view retains its full root allocation.

Raw results: [current native methods](results/m1-pro-numpy-interop.json), [before NumPy integration](results/m1-pro-optimized.json), [previous small/medium](results/m1-pro.json), [previous large](results/m1-pro-large.json), [initial baseline](results/m1-pro-baseline.json).
[Per-method CSV](results/methods.csv) includes dataset size, result retained size, additional peak bytes, sample variability, and timings.

## Retained memory

KiB, including representation overhead. Lower is better.

| Structure | Elements | Bits | Python list | NumPy | Packed | Word-aligned |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1d | 1,024 | 2 | 8.16 | 1.11 | 0.32 | 0.32 |
| 1d | 1,024 | 5 | 8.93 | 1.11 | 0.70 | 0.74 |
| 1d | 1,024 | 7 | 11.55 | 1.11 | 0.95 | 0.96 |
| 1d | 65,536 | 2 | 512.16 | 64.11 | 16.07 | 16.07 |
| 1d | 65,536 | 5 | 512.93 | 64.11 | 40.07 | 42.74 |
| 1d | 65,536 | 7 | 515.55 | 64.11 | 56.07 | 56.96 |
| 1d | 1,048,576 | 2 | 8192.16 | 1024.11 | 256.07 | 256.07 |
| 1d | 1,048,576 | 5 | 8192.93 | 1024.11 | 640.07 | 682.74 |
| 1d | 1,048,576 | 7 | 8195.55 | 1024.11 | 896.07 | 910.30 |
| matrix | 1,024 | 2 | 9.16 | 1.12 | 0.38 | 0.38 |
| matrix | 1,024 | 5 | 9.93 | 1.12 | 0.76 | 0.80 |
| matrix | 1,024 | 7 | 12.55 | 1.12 | 1.01 | 1.02 |
| matrix | 65,536 | 2 | 576.76 | 64.12 | 16.13 | 16.13 |
| matrix | 65,536 | 5 | 577.52 | 64.12 | 40.13 | 42.80 |
| matrix | 65,536 | 7 | 580.15 | 64.12 | 56.13 | 57.02 |
| matrix | 1,048,576 | 2 | 9221.54 | 1024.12 | 256.13 | 256.13 |
| matrix | 1,048,576 | 5 | 9222.30 | 1024.12 | 640.13 | 682.80 |
| matrix | 1,048,576 | 7 | 9224.93 | 1024.12 | 896.13 | 910.36 |
| ragged | 1,024 | 2 | 9.33 | 1.42 | 0.52 | 0.52 |
| ragged | 1,024 | 5 | 9.99 | 1.41 | 0.89 | 0.94 |
| ragged | 1,024 | 7 | 12.80 | 1.43 | 1.16 | 1.17 |
| ragged | 65,536 | 2 | 580.21 | 72.20 | 24.05 | 24.05 |
| ragged | 65,536 | 5 | 581.85 | 72.34 | 48.19 | 50.86 |
| ragged | 65,536 | 7 | 583.48 | 72.20 | 64.05 | 64.95 |
| ragged | 1,048,576 | 2 | 9281.62 | 1151.76 | 383.61 | 383.61 |
| ragged | 1,048,576 | 5 | 9275.13 | 1150.87 | 766.72 | 809.39 |
| ragged | 1,048,576 | 7 | 9282.22 | 1151.33 | 1023.18 | 1037.41 |

For 1D, bytes/str use approximately one byte per element plus a single object header; see the CSV for exact sizes.
Ragged offsets are an additional eight bytes per row boundary, so short rows reduce the relative packing benefit.

## Per-method execution time

Microseconds per operation. `—` means no corresponding supported case. Lower is better.

### 1d, 1,024 elements, 2 bits

| Method | python-list | python-bytes | python-str | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| construct | 3.075 | 0.195 | 0.148 | 0.506 | 0.285 | 0.291 |
| count | 8.631 | 0.389 | 0.398 | 0.811 | 0.061 | 0.061 |
| equal | 0.678 | 0.058 | 0.057 | 1.020 | 0.042 | 0.044 |
| find | 3.733 | 0.343 | 0.380 | 0.408 | 0.324 | 0.303 |
| gather | 3.326 | 5.229 | 5.315 | 0.307 | 0.262 | 0.285 |
| gather-list | — | — | — | 6.430 | 1.974 | 1.944 |
| get | 0.034 | 0.040 | 0.046 | 0.058 | 0.043 | 0.043 |
| iterate-sum | 2.466 | 2.519 | 9.897 | 28.140 | 4.303 | 4.325 |
| random-get-sum | 7.948 | 9.640 | 8.046 | 17.076 | 10.119 | 10.023 |
| set | 0.047 | — | — | 0.071 | 0.057 | 0.056 |
| slice-copy | 0.738 | 0.092 | 0.096 | 0.252 | 0.087 | 0.093 |
| slice-view | — | — | — | 0.095 | 0.059 | 0.059 |

### 1d, 1,024 elements, 5 bits

| Method | python-list | python-bytes | python-str | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| construct | 3.054 | 0.199 | 0.148 | 0.512 | 0.368 | 0.378 |
| count | 9.177 | 0.389 | 0.389 | 0.823 | 0.101 | 0.083 |
| equal | 0.711 | 0.060 | 0.058 | 1.030 | 0.055 | 0.069 |
| find | 3.742 | 0.375 | 0.406 | 0.442 | 0.315 | 0.339 |
| gather | 3.324 | 5.505 | 5.363 | 0.312 | 0.373 | 0.292 |
| gather-list | — | — | — | 6.471 | 2.075 | 2.006 |
| get | 0.035 | 0.040 | 0.046 | 0.059 | 0.043 | 0.043 |
| iterate-sum | 2.473 | 2.583 | 10.155 | 28.500 | 5.164 | 4.386 |
| random-get-sum | 8.052 | 9.705 | 8.103 | 17.098 | 10.316 | 10.161 |
| set | 0.047 | — | — | 0.070 | 0.056 | 0.056 |
| slice-copy | 0.743 | 0.094 | 0.097 | 0.256 | 0.091 | 0.114 |
| slice-view | — | — | — | 0.097 | 0.060 | 0.060 |

### 1d, 1,024 elements, 7 bits

| Method | python-list | python-bytes | python-str | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| construct | 3.106 | 0.198 | 0.148 | 0.509 | 0.387 | 0.379 |
| count | 9.224 | 0.383 | 0.391 | 0.806 | 0.102 | 0.092 |
| equal | 0.688 | 0.059 | 0.058 | 1.010 | 0.062 | 0.085 |
| find | 3.815 | 0.386 | 0.418 | 0.457 | 0.367 | 0.375 |
| gather | 3.356 | 5.323 | 5.351 | 0.305 | 0.367 | 0.328 |
| gather-list | — | — | — | 6.561 | 2.121 | 2.126 |
| get | 0.034 | 0.040 | 0.048 | 0.057 | 0.044 | 0.044 |
| iterate-sum | 2.452 | 2.583 | 10.066 | 28.403 | 5.510 | 4.690 |
| random-get-sum | 8.007 | 9.829 | 8.196 | 17.511 | 10.558 | 10.388 |
| set | 0.047 | — | — | 0.072 | 0.057 | 0.058 |
| slice-copy | 0.741 | 0.094 | 0.098 | 0.250 | 0.097 | 0.120 |
| slice-view | — | — | — | 0.097 | 0.061 | 0.062 |

### 1d, 65,536 elements, 2 bits

| Method | python-list | python-bytes | python-str | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| construct | 195.141 | 4.246 | 3.617 | 1.714 | 5.346 | 5.364 |
| count | 574.750 | 20.472 | 20.461 | 4.723 | 0.705 | 0.706 |
| equal | 41.295 | 1.853 | 1.777 | 4.122 | 0.471 | 0.479 |
| find | 219.984 | 4.328 | 4.368 | 5.293 | 1.539 | 1.329 |
| gather | 3.392 | 5.168 | 5.183 | 0.307 | 0.263 | 0.278 |
| gather-list | — | — | — | 5.735 | 1.748 | 1.655 |
| get | 0.034 | 0.041 | 0.046 | 0.059 | 0.042 | 0.042 |
| iterate-sum | 152.730 | 158.306 | 625.792 | 1767.427 | 265.908 | 273.137 |
| random-get-sum | 7.384 | 9.012 | 7.490 | 15.842 | 9.528 | 9.414 |
| set | 0.046 | — | — | 0.072 | 0.057 | 0.056 |
| slice-copy | 41.233 | 0.745 | 0.543 | 0.867 | 0.220 | 0.222 |
| slice-view | — | — | — | 0.095 | 0.060 | 0.059 |

### 1d, 65,536 elements, 5 bits

| Method | python-list | python-bytes | python-str | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| construct | 198.012 | 4.112 | 3.892 | 1.346 | 7.878 | 7.894 |
| count | 583.422 | 20.543 | 20.403 | 4.719 | 3.275 | 1.759 |
| equal | 47.149 | 1.885 | 1.779 | 4.174 | 1.109 | 1.166 |
| find | 238.087 | 27.462 | 27.593 | 29.301 | 12.395 | 14.001 |
| gather | 3.372 | 5.180 | 5.194 | 0.307 | 0.401 | 0.294 |
| gather-list | — | — | — | 5.844 | 1.976 | 1.747 |
| get | 0.033 | 0.040 | 0.046 | 0.059 | 0.045 | 0.044 |
| iterate-sum | 156.493 | 160.318 | 631.990 | 1763.125 | 320.807 | 270.523 |
| random-get-sum | 7.328 | 9.033 | 7.540 | 16.185 | 9.920 | 9.626 |
| set | 0.046 | — | — | 0.070 | 0.058 | 0.057 |
| slice-copy | 40.904 | 0.504 | 0.525 | 0.849 | 0.468 | 0.681 |
| slice-view | — | — | — | 0.097 | 0.061 | 0.060 |

### 1d, 65,536 elements, 7 bits

| Method | python-list | python-bytes | python-str | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| construct | 199.142 | 4.198 | 3.529 | 1.367 | 8.523 | 6.754 |
| count | 592.734 | 20.497 | 20.465 | 4.768 | 3.260 | 2.375 |
| equal | 41.739 | 1.902 | 1.808 | 4.192 | 1.560 | 1.595 |
| find | 242.035 | 26.707 | 26.665 | 28.507 | 15.353 | 15.159 |
| gather | 3.477 | 5.056 | 5.230 | 0.313 | 0.368 | 0.329 |
| gather-list | — | — | — | 5.862 | 2.067 | 1.819 |
| get | 0.034 | 0.040 | 0.045 | 0.059 | 0.044 | 0.044 |
| iterate-sum | 155.635 | 159.980 | 635.875 | 1801.979 | 341.508 | 290.083 |
| random-get-sum | 7.285 | 9.016 | 7.731 | 16.197 | 9.850 | 9.678 |
| set | 0.047 | — | — | 0.071 | 0.057 | 0.057 |
| slice-copy | 41.822 | 0.543 | 0.736 | 0.844 | 0.600 | 0.859 |
| slice-view | — | — | — | 0.097 | 0.061 | 0.060 |

### 1d, 1,048,576 elements, 2 bits

| Method | python-list | python-bytes | python-str | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| construct | 3174.625 | 42.995 | 58.364 | 19.595 | 82.555 | 82.253 |
| count | 9230.917 | 331.701 | 332.305 | 62.556 | 10.372 | 10.609 |
| equal | 770.646 | 27.216 | 27.474 | 48.849 | 6.679 | 6.745 |
| find | 3582.562 | 71.115 | 76.246 | 90.215 | 18.261 | 32.343 |
| gather | 3.480 | 5.242 | 5.263 | 0.307 | 0.264 | 0.283 |
| gather-list | — | — | — | 5.727 | 1.638 | 1.665 |
| get | 0.034 | 0.040 | 0.046 | 0.059 | 0.042 | 0.042 |
| iterate-sum | 2454.271 | 2521.250 | 10133.459 | 28819.250 | 4258.708 | 4330.541 |
| random-get-sum | 7.435 | 9.021 | 7.541 | 16.141 | 9.404 | 9.381 |
| set | 0.046 | — | — | 0.070 | 0.057 | 0.057 |
| slice-copy | 661.469 | 8.794 | 9.464 | 9.021 | 2.372 | 2.381 |
| slice-view | — | — | — | 0.095 | 0.059 | 0.061 |

### 1d, 1,048,576 elements, 5 bits

| Method | python-list | python-bytes | python-str | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| construct | 3199.167 | 42.166 | 58.850 | 19.114 | 120.232 | 119.279 |
| count | 9521.667 | 326.560 | 335.753 | 64.158 | 50.885 | 27.938 |
| equal | 769.771 | 27.262 | 27.359 | 49.928 | 16.824 | 17.905 |
| find | 3907.416 | 441.320 | 441.391 | 461.281 | 207.107 | 218.167 |
| gather | 3.542 | 5.246 | 5.357 | 0.311 | 0.399 | 0.293 |
| gather-list | — | — | — | 5.841 | 1.927 | 1.742 |
| get | 0.034 | 0.040 | 0.046 | 0.058 | 0.043 | 0.043 |
| iterate-sum | 2525.792 | 2563.729 | 10196.042 | 28604.542 | 5207.792 | 4340.125 |
| random-get-sum | 7.421 | 9.135 | 7.502 | 16.142 | 9.726 | 9.673 |
| set | 0.047 | — | — | 0.070 | 0.057 | 0.057 |
| slice-copy | 671.682 | 8.758 | 8.840 | 9.020 | 5.608 | 8.993 |
| slice-view | — | — | — | 0.097 | 0.060 | 0.060 |

### 1d, 1,048,576 elements, 7 bits

| Method | python-list | python-bytes | python-str | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| construct | 3244.188 | 41.181 | 58.797 | 19.509 | 130.869 | 103.719 |
| count | 9517.084 | 338.479 | 332.234 | 63.180 | 51.653 | 37.107 |
| equal | 690.198 | 27.178 | 27.396 | 49.454 | 23.767 | 23.948 |
| find | 3900.688 | 425.781 | 423.503 | 440.221 | 242.276 | 239.353 |
| gather | 3.522 | 5.345 | 5.340 | 0.311 | 0.387 | 0.331 |
| gather-list | — | — | — | 5.831 | 2.097 | 1.790 |
| get | 0.034 | 0.040 | 0.046 | 0.059 | 0.044 | 0.045 |
| iterate-sum | 2533.313 | 2567.000 | 10121.542 | 28798.167 | 5454.708 | 4639.313 |
| random-get-sum | 7.448 | 9.199 | 7.664 | 16.130 | 9.877 | 9.690 |
| set | 0.047 | — | — | 0.071 | 0.057 | 0.057 |
| slice-copy | 658.912 | 8.807 | 8.534 | 9.033 | 7.634 | 11.911 |
| slice-view | — | — | — | 0.096 | 0.060 | 0.060 |

### matrix, 1,024 elements, 2 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2.222 | 17.814 | 16.355 | 16.187 |
| count | 9.094 | 0.838 | 0.084 | 0.083 |
| equal | 0.921 | 1.026 | 0.057 | 0.057 |
| get | 0.038 | 0.082 | 0.054 | 0.054 |
| row-copy | 0.144 | 0.217 | 0.073 | 0.075 |
| row-view | — | 0.081 | 0.046 | 0.046 |
| set | 0.044 | 0.088 | 0.064 | 0.064 |

### matrix, 1,024 elements, 5 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2.211 | 18.017 | 16.421 | 15.930 |
| count | 9.751 | 0.870 | 0.107 | 0.088 |
| equal | 0.916 | 1.048 | 0.066 | 0.078 |
| get | 0.038 | 0.082 | 0.054 | 0.055 |
| row-copy | 0.142 | 0.217 | 0.073 | 0.083 |
| row-view | — | 0.082 | 0.046 | 0.046 |
| set | 0.044 | 0.088 | 0.065 | 0.065 |

### matrix, 1,024 elements, 7 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2.229 | 18.130 | 16.972 | 16.481 |
| count | 9.765 | 0.841 | 0.108 | 0.095 |
| equal | 0.924 | 1.020 | 0.075 | 0.092 |
| get | 0.038 | 0.084 | 0.055 | 0.055 |
| row-copy | 0.143 | 0.218 | 0.076 | 0.080 |
| row-view | — | 0.083 | 0.047 | 0.046 |
| set | 0.044 | 0.088 | 0.065 | 0.065 |

### matrix, 65,536 elements, 2 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 140.447 | 1131.849 | 824.568 | 825.880 |
| count | 603.599 | 4.712 | 0.715 | 0.712 |
| equal | 59.760 | 4.118 | 0.543 | 0.532 |
| get | 0.039 | 0.082 | 0.054 | 0.054 |
| row-copy | 0.143 | 0.218 | 0.074 | 0.075 |
| row-view | — | 0.083 | 0.047 | 0.047 |
| set | 0.045 | 0.089 | 0.065 | 0.065 |

### matrix, 65,536 elements, 5 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 140.275 | 1139.031 | 849.922 | 829.469 |
| count | 615.891 | 4.789 | 3.220 | 1.770 |
| equal | 57.451 | 4.257 | 1.271 | 1.181 |
| get | 0.039 | 0.083 | 0.056 | 0.055 |
| row-copy | 0.145 | 0.222 | 0.075 | 0.084 |
| row-view | — | 0.084 | 0.047 | 0.047 |
| set | 0.046 | 0.091 | 0.065 | 0.066 |

### matrix, 65,536 elements, 7 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 143.685 | 1136.500 | 881.182 | 844.089 |
| count | 624.737 | 4.870 | 3.280 | 2.346 |
| equal | 60.061 | 4.248 | 1.769 | 1.817 |
| get | 0.041 | 0.083 | 0.056 | 0.056 |
| row-copy | 0.156 | 0.222 | 0.077 | 0.080 |
| row-view | — | 0.084 | 0.048 | 0.048 |
| set | 0.049 | 0.090 | 0.066 | 0.066 |

### matrix, 1,048,576 elements, 2 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2678.750 | 18281.667 | 15596.542 | 15414.917 |
| count | 9722.625 | 59.898 | 10.564 | 10.563 |
| equal | 976.693 | 46.839 | 7.950 | 7.833 |
| get | 0.038 | 0.082 | 0.053 | 0.055 |
| row-copy | 0.145 | 0.218 | 0.075 | 0.077 |
| row-view | — | 0.082 | 0.048 | 0.047 |
| set | 0.045 | 0.090 | 0.066 | 0.065 |

### matrix, 1,048,576 elements, 5 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2706.125 | 18325.083 | 16390.791 | 15656.250 |
| count | 10107.208 | 65.382 | 52.301 | 27.874 |
| equal | 979.880 | 42.764 | 19.919 | 17.999 |
| get | 0.039 | 0.082 | 0.057 | 0.056 |
| row-copy | 0.147 | 0.218 | 0.077 | 0.084 |
| row-view | — | 0.084 | 0.049 | 0.048 |
| set | 0.047 | 0.088 | 0.067 | 0.066 |

### matrix, 1,048,576 elements, 7 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2811.542 | 18607.500 | 16313.833 | 15667.667 |
| count | 10016.083 | 62.993 | 52.014 | 37.315 |
| equal | 979.615 | 49.468 | 27.505 | 27.734 |
| get | 0.039 | 0.083 | 0.056 | 0.056 |
| row-copy | 0.147 | 0.221 | 0.077 | 0.081 |
| row-view | — | 0.084 | 0.048 | 0.047 |
| set | 0.046 | 0.090 | 0.066 | 0.066 |

### ragged, 1,024 elements, 2 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2.519 | 28.031 | 16.204 | 16.140 |
| count | 9.148 | 0.818 | 0.082 | 0.082 |
| equal | 0.925 | 2.190 | 0.058 | 0.059 |
| get | 0.038 | 0.120 | 0.055 | 0.055 |
| row-copy | 0.140 | 0.393 | 0.074 | 0.143 |
| row-view | — | 0.232 | 0.046 | 0.046 |
| set | 0.045 | 0.128 | 0.065 | 0.064 |

### ragged, 1,024 elements, 5 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2.577 | 28.469 | 17.006 | 16.433 |
| count | 9.755 | 0.819 | 0.107 | 0.090 |
| equal | 0.926 | 2.205 | 0.070 | 0.082 |
| get | 0.038 | 0.120 | 0.056 | 0.056 |
| row-copy | 0.074 | 0.395 | 0.074 | 0.092 |
| row-view | — | 0.236 | 0.047 | 0.047 |
| set | 0.044 | 0.127 | 0.066 | 0.065 |

### ragged, 1,024 elements, 7 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2.750 | 28.506 | 17.438 | 16.876 |
| count | 9.849 | 0.830 | 0.108 | 0.098 |
| equal | 0.938 | 2.227 | 0.075 | 0.096 |
| get | 0.039 | 0.123 | 0.056 | 0.057 |
| row-copy | 0.189 | 0.384 | 0.076 | 0.088 |
| row-view | — | 0.238 | 0.047 | 0.047 |
| set | 0.045 | 0.130 | 0.065 | 0.065 |

### ragged, 65,536 elements, 2 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 168.238 | 1641.698 | 856.073 | 854.615 |
| count | 603.487 | 4.682 | 0.710 | 0.710 |
| equal | 60.458 | 5.722 | 0.733 | 0.729 |
| get | 0.039 | 0.122 | 0.055 | 0.055 |
| row-copy | 0.222 | 0.381 | 0.073 | 0.089 |
| row-view | — | 0.233 | 0.047 | 0.047 |
| set | 0.045 | 0.129 | 0.066 | 0.066 |

### ragged, 65,536 elements, 5 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 169.620 | 1667.500 | 889.839 | 876.240 |
| count | 617.703 | 4.750 | 3.220 | 1.773 |
| equal | 58.983 | 5.826 | 1.361 | 1.464 |
| get | 0.038 | 0.122 | 0.055 | 0.055 |
| row-copy | 0.203 | 0.379 | 0.075 | 0.088 |
| row-view | — | 0.233 | 0.047 | 0.047 |
| set | 0.045 | 0.129 | 0.065 | 0.065 |

### ragged, 65,536 elements, 7 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 171.116 | 1661.917 | 912.432 | 877.641 |
| count | 626.995 | 4.826 | 3.282 | 2.380 |
| equal | 60.221 | 5.881 | 1.811 | 1.830 |
| get | 0.039 | 0.124 | 0.056 | 0.056 |
| row-copy | 0.220 | 0.383 | 0.076 | 0.080 |
| row-view | — | 0.237 | 0.048 | 0.048 |
| set | 0.046 | 0.131 | 0.067 | 0.068 |

### ragged, 1,048,576 elements, 2 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2895.625 | 26717.875 | 15182.750 | 15105.584 |
| count | 9780.458 | 63.161 | 10.544 | 10.684 |
| equal | 1086.365 | 55.072 | 10.608 | 10.821 |
| get | 0.038 | 0.124 | 0.055 | 0.055 |
| row-copy | 0.214 | 0.383 | 0.075 | 0.080 |
| row-view | — | 0.237 | 0.047 | 0.049 |
| set | 0.046 | 0.130 | 0.067 | 0.065 |

### ragged, 1,048,576 elements, 5 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2890.333 | 26754.834 | 16726.042 | 16257.083 |
| count | 9895.917 | 63.956 | 50.975 | 28.444 |
| equal | 1100.995 | 54.546 | 20.595 | 21.518 |
| get | 0.038 | 0.124 | 0.056 | 0.056 |
| row-copy | 0.109 | 0.389 | 0.075 | 0.078 |
| row-view | — | 0.237 | 0.048 | 0.048 |
| set | 0.046 | 0.132 | 0.065 | 0.067 |

### ragged, 1,048,576 elements, 7 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2899.250 | 26707.791 | 17305.084 | 16290.209 |
| count | 10015.583 | 64.093 | 51.567 | 37.230 |
| equal | 1132.328 | 54.605 | 27.087 | 27.507 |
| get | 0.040 | 0.124 | 0.056 | 0.057 |
| row-copy | 0.061 | 0.384 | 0.074 | 0.080 |
| row-view | — | 0.233 | 0.047 | 0.048 |
| set | 0.047 | 0.132 | 0.067 | 0.067 |

## Optimization versus the initial C implementation

65,536 elements; matched operations only. Initial source commit: `bc57700`.
Nested construction is excluded because the initial NumPy baseline preflattened its input; the final runner corrects this.

| Structure | Bits | Layout | Method | Initial µs | Final µs | Initial/final |
| --- | ---: | --- | --- | ---: | ---: | ---: |
| 1d | 2 | packed | slice-copy | 80.408 | 0.220 | 365.1× |
| 1d | 2 | packed | equal | 105.757 | 0.471 | 224.7× |
| 1d | 2 | packed | count | 63.009 | 0.705 | 89.4× |
| 1d | 2 | packed | find | 28.606 | 1.539 | 18.6× |
| 1d | 2 | word-aligned | slice-copy | 81.597 | 0.222 | 367.8× |
| 1d | 2 | word-aligned | equal | 105.720 | 0.479 | 220.8× |
| 1d | 2 | word-aligned | count | 63.174 | 0.706 | 89.5× |
| 1d | 2 | word-aligned | find | 25.323 | 1.329 | 19.0× |
| matrix | 2 | packed | get | 0.223 | 0.054 | 4.1× |
| matrix | 2 | word-aligned | get | 0.224 | 0.054 | 4.1× |
| ragged | 2 | packed | get | 0.430 | 0.055 | 7.9× |
| ragged | 2 | word-aligned | get | 0.432 | 0.055 | 7.9× |
| 1d | 5 | packed | slice-copy | 78.634 | 0.468 | 167.9× |
| 1d | 5 | packed | equal | 164.810 | 1.109 | 148.6× |
| 1d | 5 | packed | count | 93.960 | 3.275 | 28.7× |
| 1d | 5 | packed | find | 150.878 | 12.395 | 12.2× |
| 1d | 5 | word-aligned | slice-copy | 84.343 | 0.681 | 123.8× |
| 1d | 5 | word-aligned | equal | 112.460 | 1.166 | 96.4× |
| 1d | 5 | word-aligned | count | 70.370 | 1.759 | 40.0× |
| 1d | 5 | word-aligned | find | 156.780 | 14.001 | 11.2× |
| matrix | 5 | packed | get | 0.223 | 0.056 | 4.0× |
| matrix | 5 | word-aligned | get | 0.224 | 0.055 | 4.0× |
| ragged | 5 | packed | get | 0.437 | 0.055 | 7.9× |
| ragged | 5 | word-aligned | get | 0.436 | 0.055 | 7.9× |
| 1d | 7 | packed | slice-copy | 80.970 | 0.600 | 135.0× |
| 1d | 7 | packed | equal | 168.250 | 1.560 | 107.9× |
| 1d | 7 | packed | count | 95.047 | 3.260 | 29.2× |
| 1d | 7 | packed | find | 131.645 | 15.353 | 8.6× |
| 1d | 7 | word-aligned | slice-copy | 81.896 | 0.859 | 95.3× |
| 1d | 7 | word-aligned | equal | 146.509 | 1.595 | 91.8× |
| 1d | 7 | word-aligned | count | 83.553 | 2.375 | 35.2× |
| 1d | 7 | word-aligned | find | 132.121 | 15.159 | 8.7× |
| matrix | 7 | packed | get | 0.224 | 0.056 | 4.0× |
| matrix | 7 | word-aligned | get | 0.224 | 0.056 | 4.0× |
| ragged | 7 | packed | get | 0.436 | 0.056 | 7.7× |
| ragged | 7 | word-aligned | get | 0.436 | 0.056 | 7.8× |

## Remaining optimization targets

- Packing construction has validation and conversion costs; bytes/str/NumPy construction can be faster.
- Single-item list access and Python iteration remain strong baselines; not every method wins.
- Word-aligned slices starting within a word require realignment when copied.
- Long needles use KMP with linear worst-case complexity; more pattern distributions and lengths need measurement.
- Skewed workloads, cold-cache scans, dense bit-width sweeps, and hardware-isolated measurements are not covered by this run.
