# Measured performance

Measured on Apple M1 Pro, ARM64 macOS, 2026-09-13.

CPython `3.14.7`, NumPy `2.5.3`; clang `-O3 -mcpu=apple-m1`.
Medians of repeated adaptive timing batches. Each result is verified before timing.

## Measurement boundaries

- The machine was not isolated: existing services were left running; recorded load averages are in the JSON metadata. No affinity or cold-cache control was used.
- Inputs are seeded uniform small integers; these are workload-specific results, not universal speedups.
- `get` measures a single Python-level call; `random-get-sum` reads 256 prepared indices through Python and normalizes scalar values.
- `iterate-sum` deliberately iterates in Python; it is not NumPy's native `sum` reduction.
- `find` uses an eight-symbol repeated-maximum needle. An early match may end the scan. Do not compare search times across widths as equal amounts of work.
- Python-list and NumPy `find` include conversion to bytes; bytes/str use their native search. tightarray includes needle construction.
- `gather` uses prepared native `intp` buffers for NumPy and tightarray; `gather-list` passes the same Python list to both. Older JSON used different input formats and is not a matched gather baseline.
- Nested construction uses the same Python rows for every implementation; NumPy ragged includes flattening and offsets construction.
- Retained size counts owned buffers, object headers, shared objects once, and allocations kept alive by views. It is not RSS.
- Additional peak bytes are measured separately with tracemalloc: PyMem and NumPy-tracked allocations are included; untracked system allocations are excluded.
- View creation and copying are separate methods. An array view retains its full root allocation.

Raw results: [optimized](results/m1-pro-optimized.json), [previous small/medium](results/m1-pro.json), [previous large](results/m1-pro-large.json), [initial baseline](results/m1-pro-baseline.json).
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
| construct | 3.033 | 0.194 | 0.147 | 0.515 | 0.282 | 0.288 |
| count | 8.431 | 0.388 | 0.394 | 0.804 | 0.060 | 0.060 |
| equal | 0.675 | 0.058 | 0.056 | 1.019 | 0.040 | 0.040 |
| find | 3.704 | 0.341 | 0.381 | 0.406 | 0.324 | 0.304 |
| gather | 3.291 | 5.137 | 5.223 | 0.305 | 0.260 | 0.274 |
| gather-list | — | — | — | 6.377 | 1.957 | 1.942 |
| get | 0.034 | 0.040 | 0.045 | 0.057 | 0.042 | 0.042 |
| iterate-sum | 2.415 | 2.562 | 9.881 | 27.819 | 4.289 | 4.370 |
| random-get-sum | 7.834 | 9.619 | 8.040 | 17.020 | 10.081 | 10.203 |
| set | 0.046 | — | — | 0.070 | 0.056 | 0.056 |
| slice-copy | 0.739 | 0.092 | 0.096 | 0.250 | 0.086 | 0.090 |
| slice-view | — | — | — | 0.095 | 0.059 | 0.060 |

### 1d, 1,024 elements, 5 bits

| Method | python-list | python-bytes | python-str | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| construct | 3.031 | 0.196 | 0.147 | 0.515 | 0.363 | 0.374 |
| count | 9.092 | 0.383 | 0.390 | 0.813 | 0.101 | 0.082 |
| equal | 0.675 | 0.059 | 0.058 | 1.017 | 0.051 | 0.065 |
| find | 3.870 | 0.373 | 0.406 | 0.437 | 0.324 | 0.341 |
| gather | 3.214 | 5.262 | 5.361 | 0.306 | 0.375 | 0.287 |
| gather-list | — | — | — | 6.442 | 2.067 | 2.052 |
| get | 0.034 | 0.040 | 0.045 | 0.058 | 0.043 | 0.043 |
| iterate-sum | 2.472 | 2.573 | 10.051 | 27.871 | 5.151 | 4.391 |
| random-get-sum | 7.925 | 9.936 | 8.199 | 17.077 | 10.505 | 10.299 |
| set | 0.047 | — | — | 0.070 | 0.056 | 0.056 |
| slice-copy | 0.738 | 0.093 | 0.098 | 0.250 | 0.091 | 0.114 |
| slice-view | — | — | — | 0.094 | 0.060 | 0.060 |

### 1d, 1,024 elements, 7 bits

| Method | python-list | python-bytes | python-str | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| construct | 3.032 | 0.198 | 0.149 | 0.524 | 0.383 | 0.374 |
| count | 9.225 | 0.383 | 0.390 | 0.806 | 0.102 | 0.091 |
| equal | 0.688 | 0.059 | 0.058 | 1.039 | 0.057 | 0.080 |
| find | 3.839 | 0.413 | 0.418 | 0.488 | 0.366 | 0.374 |
| gather | 3.203 | 5.288 | 5.167 | 0.311 | 0.360 | 0.328 |
| gather-list | — | — | — | 6.451 | 2.116 | 2.092 |
| get | 0.033 | 0.040 | 0.045 | 0.061 | 0.043 | 0.044 |
| iterate-sum | 2.445 | 2.560 | 10.011 | 28.403 | 5.488 | 4.670 |
| random-get-sum | 7.999 | 9.771 | 8.256 | 17.301 | 10.563 | 10.297 |
| set | 0.047 | — | — | 0.071 | 0.056 | 0.058 |
| slice-copy | 0.741 | 0.093 | 0.096 | 0.256 | 0.095 | 0.117 |
| slice-view | — | — | — | 0.097 | 0.060 | 0.060 |

### 1d, 65,536 elements, 2 bits

| Method | python-list | python-bytes | python-str | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| construct | 195.510 | 4.240 | 3.497 | 1.329 | 5.342 | 5.444 |
| count | 569.484 | 20.377 | 20.389 | 4.680 | 0.703 | 0.717 |
| equal | 40.827 | 1.837 | 1.781 | 4.065 | 0.464 | 0.476 |
| find | 215.092 | 4.268 | 4.368 | 5.385 | 1.482 | 1.336 |
| gather | 3.254 | 4.932 | 5.063 | 0.305 | 0.262 | 0.279 |
| gather-list | — | — | — | 5.741 | 1.649 | 1.710 |
| get | 0.034 | 0.040 | 0.045 | 0.057 | 0.042 | 0.042 |
| iterate-sum | 154.995 | 157.091 | 626.615 | 1762.969 | 265.689 | 270.193 |
| random-get-sum | 7.184 | 8.978 | 7.486 | 15.857 | 9.533 | 9.692 |
| set | 0.046 | — | — | 0.070 | 0.056 | 0.057 |
| slice-copy | 40.961 | 0.495 | 0.523 | 0.846 | 0.232 | 0.223 |
| slice-view | — | — | — | 0.094 | 0.059 | 0.062 |

### 1d, 65,536 elements, 5 bits

| Method | python-list | python-bytes | python-str | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| construct | 195.331 | 4.365 | 3.475 | 1.364 | 7.803 | 7.970 |
| count | 583.016 | 20.383 | 20.407 | 4.770 | 3.210 | 1.793 |
| equal | 47.027 | 1.843 | 1.815 | 4.171 | 1.091 | 1.184 |
| find | 238.695 | 27.487 | 27.440 | 29.218 | 12.352 | 13.967 |
| gather | 3.301 | 5.158 | 5.149 | 0.311 | 0.392 | 0.297 |
| gather-list | — | — | — | 5.835 | 1.986 | 1.744 |
| get | 0.034 | 0.040 | 0.046 | 0.058 | 0.043 | 0.044 |
| iterate-sum | 155.281 | 159.449 | 638.958 | 1787.667 | 319.823 | 270.669 |
| random-get-sum | 7.309 | 9.135 | 7.628 | 16.156 | 9.783 | 9.558 |
| set | 0.046 | — | — | 0.071 | 0.057 | 0.057 |
| slice-copy | 40.944 | 0.509 | 0.539 | 0.848 | 0.448 | 0.674 |
| slice-view | — | — | — | 0.094 | 0.060 | 0.060 |

### 1d, 65,536 elements, 7 bits

| Method | python-list | python-bytes | python-str | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| construct | 198.793 | 4.190 | 3.593 | 1.361 | 8.457 | 6.835 |
| count | 596.615 | 20.531 | 20.416 | 4.769 | 3.271 | 2.372 |
| equal | 41.577 | 1.867 | 1.803 | 4.172 | 1.553 | 1.591 |
| find | 247.879 | 26.618 | 26.626 | 28.285 | 15.366 | 15.169 |
| gather | 3.386 | 5.088 | 5.185 | 0.311 | 0.367 | 0.323 |
| gather-list | — | — | — | 5.850 | 2.104 | 1.818 |
| get | 0.034 | 0.040 | 0.045 | 0.059 | 0.044 | 0.044 |
| iterate-sum | 156.070 | 160.439 | 633.932 | 1790.167 | 335.091 | 290.115 |
| random-get-sum | 7.259 | 9.096 | 7.523 | 16.114 | 9.810 | 9.645 |
| set | 0.047 | — | — | 0.072 | 0.057 | 0.056 |
| slice-copy | 41.767 | 0.689 | 0.533 | 0.799 | 0.601 | 0.856 |
| slice-view | — | — | — | 0.096 | 0.061 | 0.061 |

### 1d, 1,048,576 elements, 2 bits

| Method | python-list | python-bytes | python-str | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| construct | 3160.667 | 46.725 | 58.523 | 18.902 | 83.958 | 83.796 |
| count | 9377.791 | 334.964 | 325.732 | 63.710 | 10.542 | 10.542 |
| equal | 688.344 | 26.979 | 27.074 | 45.656 | 6.669 | 6.664 |
| find | 3519.771 | 67.726 | 76.371 | 91.368 | 30.436 | 24.690 |
| gather | 3.440 | 5.122 | 5.074 | 0.307 | 0.265 | 0.280 |
| gather-list | — | — | — | 5.825 | 1.654 | 1.626 |
| get | 0.034 | 0.041 | 0.045 | 0.058 | 0.043 | 0.043 |
| iterate-sum | 2467.979 | 2580.375 | 10263.708 | 28287.625 | 4319.292 | 4324.021 |
| random-get-sum | 7.415 | 8.956 | 7.507 | 16.127 | 9.517 | 9.366 |
| set | 0.048 | — | — | 0.071 | 0.057 | 0.056 |
| slice-copy | 655.536 | 8.610 | 8.717 | 8.984 | 2.367 | 2.347 |
| slice-view | — | — | — | 0.096 | 0.060 | 0.060 |

### 1d, 1,048,576 elements, 5 bits

| Method | python-list | python-bytes | python-str | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| construct | 3202.396 | 45.323 | 58.548 | 20.818 | 119.913 | 121.777 |
| count | 9520.667 | 330.078 | 331.492 | 62.447 | 51.699 | 27.874 |
| equal | 786.026 | 27.063 | 27.029 | 42.407 | 16.878 | 17.885 |
| find | 3927.146 | 440.922 | 455.161 | 457.898 | 207.686 | 216.160 |
| gather | 3.328 | 5.153 | 5.215 | 0.308 | 0.393 | 0.298 |
| gather-list | — | — | — | 5.834 | 1.923 | 1.738 |
| get | 0.034 | 0.040 | 0.045 | 0.059 | 0.045 | 0.044 |
| iterate-sum | 2526.000 | 2553.333 | 10115.375 | 28813.375 | 5210.208 | 4328.000 |
| random-get-sum | 7.405 | 9.151 | 7.706 | 16.093 | 9.731 | 9.667 |
| set | 0.047 | — | — | 0.071 | 0.057 | 0.056 |
| slice-copy | 668.005 | 8.644 | 8.711 | 9.034 | 5.584 | 8.961 |
| slice-view | — | — | — | 0.096 | 0.059 | 0.060 |

### 1d, 1,048,576 elements, 7 bits

| Method | python-list | python-bytes | python-str | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| construct | 3174.563 | 43.541 | 59.415 | 20.580 | 131.087 | 103.740 |
| count | 9484.875 | 327.234 | 337.315 | 64.012 | 52.326 | 37.132 |
| equal | 689.344 | 27.524 | 26.950 | 49.288 | 23.696 | 24.104 |
| find | 3882.041 | 423.617 | 423.294 | 456.854 | 247.281 | 239.579 |
| gather | 3.424 | 5.180 | 5.200 | 0.311 | 0.383 | 0.330 |
| gather-list | — | — | — | 5.980 | 2.105 | 1.793 |
| get | 0.034 | 0.041 | 0.046 | 0.059 | 0.044 | 0.045 |
| iterate-sum | 2526.083 | 2536.479 | 10180.667 | 28584.417 | 5472.584 | 4647.229 |
| random-get-sum | 7.363 | 9.133 | 7.658 | 16.108 | 9.861 | 9.662 |
| set | 0.047 | — | — | 0.072 | 0.057 | 0.057 |
| slice-copy | 667.214 | 8.746 | 8.787 | 9.041 | 7.735 | 11.928 |
| slice-view | — | — | — | 0.096 | 0.060 | 0.060 |

### matrix, 1,024 elements, 2 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2.230 | 17.730 | 16.010 | 16.025 |
| count | 9.021 | 0.830 | 0.082 | 0.082 |
| equal | 0.915 | 1.020 | 0.045 | 0.045 |
| get | 0.038 | 0.082 | 0.053 | 0.055 |
| row-copy | 0.143 | 0.216 | 0.071 | 0.075 |
| row-view | — | 0.081 | 0.046 | 0.046 |
| set | 0.044 | 0.087 | 0.066 | 0.064 |

### matrix, 1,024 elements, 5 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2.220 | 18.071 | 16.318 | 16.273 |
| count | 9.736 | 0.827 | 0.107 | 0.089 |
| equal | 0.917 | 1.028 | 0.056 | 0.070 |
| get | 0.038 | 0.082 | 0.055 | 0.054 |
| row-copy | 0.141 | 0.216 | 0.073 | 0.083 |
| row-view | — | 0.082 | 0.046 | 0.047 |
| set | 0.044 | 0.089 | 0.064 | 0.065 |

### matrix, 1,024 elements, 7 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2.217 | 18.079 | 16.909 | 16.274 |
| count | 9.704 | 0.836 | 0.108 | 0.097 |
| equal | 0.920 | 1.047 | 0.063 | 0.085 |
| get | 0.038 | 0.083 | 0.055 | 0.055 |
| row-copy | 0.145 | 0.220 | 0.074 | 0.079 |
| row-view | — | 0.083 | 0.046 | 0.047 |
| set | 0.044 | 0.089 | 0.065 | 0.065 |

### matrix, 65,536 elements, 2 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 139.504 | 1117.672 | 820.401 | 844.693 |
| count | 609.924 | 4.764 | 0.709 | 0.732 |
| equal | 59.292 | 4.120 | 0.530 | 0.552 |
| get | 0.039 | 0.082 | 0.054 | 0.056 |
| row-copy | 0.143 | 0.217 | 0.072 | 0.077 |
| row-view | — | 0.082 | 0.046 | 0.048 |
| set | 0.045 | 0.088 | 0.067 | 0.067 |

### matrix, 65,536 elements, 5 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 139.272 | 1138.557 | 858.688 | 831.818 |
| count | 636.755 | 4.838 | 3.343 | 1.822 |
| equal | 57.047 | 4.251 | 1.296 | 1.274 |
| get | 0.039 | 0.082 | 0.055 | 0.057 |
| row-copy | 0.146 | 0.222 | 0.074 | 0.085 |
| row-view | — | 0.084 | 0.046 | 0.047 |
| set | 0.046 | 0.090 | 0.066 | 0.065 |

### matrix, 65,536 elements, 7 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 141.366 | 1154.083 | 880.443 | 833.453 |
| count | 612.042 | 4.863 | 3.293 | 2.378 |
| equal | 58.427 | 4.571 | 1.787 | 1.834 |
| get | 0.038 | 0.083 | 0.055 | 0.055 |
| row-copy | 0.144 | 0.223 | 0.075 | 0.081 |
| row-view | — | 0.084 | 0.047 | 0.047 |
| set | 0.046 | 0.090 | 0.066 | 0.067 |

### matrix, 1,048,576 elements, 2 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2688.875 | 18385.375 | 15344.750 | 15092.500 |
| count | 9685.792 | 62.978 | 10.352 | 10.343 |
| equal | 961.156 | 48.738 | 7.957 | 7.889 |
| get | 0.038 | 0.083 | 0.054 | 0.054 |
| row-copy | 0.143 | 0.219 | 0.073 | 0.074 |
| row-view | — | 0.083 | 0.046 | 0.046 |
| set | 0.047 | 0.090 | 0.066 | 0.065 |

### matrix, 1,048,576 elements, 5 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2761.292 | 18226.417 | 15805.250 | 15342.542 |
| count | 10060.125 | 62.878 | 50.725 | 27.972 |
| equal | 978.365 | 49.263 | 19.686 | 19.662 |
| get | 0.039 | 0.083 | 0.055 | 0.057 |
| row-copy | 0.144 | 0.221 | 0.073 | 0.083 |
| row-view | — | 0.084 | 0.046 | 0.047 |
| set | 0.046 | 0.090 | 0.066 | 0.066 |

### matrix, 1,048,576 elements, 7 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2736.250 | 18240.416 | 16237.584 | 15341.625 |
| count | 9996.042 | 64.111 | 51.611 | 37.206 |
| equal | 977.995 | 49.478 | 27.510 | 27.982 |
| get | 0.039 | 0.083 | 0.054 | 0.056 |
| row-copy | 0.146 | 0.221 | 0.075 | 0.080 |
| row-view | — | 0.084 | 0.047 | 0.047 |
| set | 0.046 | 0.089 | 0.066 | 0.067 |

### ragged, 1,024 elements, 2 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2.567 | 27.786 | 16.194 | 16.190 |
| count | 9.107 | 0.818 | 0.082 | 0.082 |
| equal | 0.923 | 2.211 | 0.048 | 0.048 |
| get | 0.038 | 0.122 | 0.054 | 0.054 |
| row-copy | 0.139 | 0.396 | 0.071 | 0.142 |
| row-view | — | 0.232 | 0.046 | 0.046 |
| set | 0.044 | 0.128 | 0.064 | 0.064 |

### ragged, 1,024 elements, 5 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2.534 | 28.262 | 16.922 | 15.996 |
| count | 9.921 | 0.822 | 0.109 | 0.088 |
| equal | 0.932 | 2.273 | 0.059 | 0.070 |
| get | 0.038 | 0.123 | 0.056 | 0.056 |
| row-copy | 0.075 | 0.386 | 0.073 | 0.091 |
| row-view | — | 0.240 | 0.047 | 0.047 |
| set | 0.046 | 0.130 | 0.065 | 0.064 |

### ragged, 1,024 elements, 7 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2.674 | 28.393 | 17.234 | 16.522 |
| count | 9.950 | 0.822 | 0.108 | 0.097 |
| equal | 0.951 | 2.270 | 0.065 | 0.086 |
| get | 0.038 | 0.123 | 0.056 | 0.056 |
| row-copy | 0.186 | 0.381 | 0.075 | 0.087 |
| row-view | — | 0.242 | 0.047 | 0.047 |
| set | 0.045 | 0.130 | 0.066 | 0.066 |

### ragged, 65,536 elements, 2 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 167.872 | 1637.875 | 862.042 | 853.521 |
| count | 598.062 | 4.705 | 0.710 | 0.709 |
| equal | 60.151 | 5.740 | 0.714 | 0.718 |
| get | 0.039 | 0.132 | 0.054 | 0.054 |
| row-copy | 0.228 | 0.378 | 0.072 | 0.089 |
| row-view | — | 0.232 | 0.046 | 0.046 |
| set | 0.045 | 0.128 | 0.065 | 0.065 |

### ragged, 65,536 elements, 5 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 166.195 | 1669.042 | 886.531 | 867.245 |
| count | 617.523 | 4.724 | 3.215 | 1.799 |
| equal | 58.923 | 5.960 | 1.361 | 1.446 |
| get | 0.038 | 0.122 | 0.055 | 0.056 |
| row-copy | 0.203 | 0.378 | 0.074 | 0.089 |
| row-view | — | 0.233 | 0.047 | 0.047 |
| set | 0.045 | 0.132 | 0.066 | 0.065 |

### ragged, 65,536 elements, 7 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 169.299 | 1679.708 | 913.896 | 869.943 |
| count | 628.062 | 4.909 | 3.247 | 2.386 |
| equal | 60.310 | 6.090 | 1.804 | 1.824 |
| get | 0.039 | 0.124 | 0.056 | 0.055 |
| row-copy | 0.218 | 0.383 | 0.076 | 0.078 |
| row-view | — | 0.238 | 0.047 | 0.048 |
| set | 0.047 | 0.132 | 0.067 | 0.067 |

### ragged, 1,048,576 elements, 2 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2828.500 | 26721.375 | 14879.250 | 15043.333 |
| count | 9796.125 | 62.898 | 10.344 | 10.351 |
| equal | 1064.083 | 53.600 | 10.608 | 10.620 |
| get | 0.039 | 0.122 | 0.054 | 0.054 |
| row-copy | 0.214 | 0.381 | 0.073 | 0.078 |
| row-view | — | 0.233 | 0.047 | 0.047 |
| set | 0.045 | 0.129 | 0.065 | 0.065 |

### ragged, 1,048,576 elements, 5 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2861.583 | 26686.333 | 16977.584 | 16199.667 |
| count | 10088.500 | 63.949 | 52.483 | 27.923 |
| equal | 1107.250 | 54.648 | 20.564 | 21.547 |
| get | 0.039 | 0.124 | 0.056 | 0.055 |
| row-copy | 0.111 | 0.387 | 0.074 | 0.076 |
| row-view | — | 0.237 | 0.046 | 0.047 |
| set | 0.046 | 0.131 | 0.066 | 0.066 |

### ragged, 1,048,576 elements, 7 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2928.042 | 26692.583 | 17085.500 | 16842.917 |
| count | 10098.417 | 64.028 | 51.525 | 37.250 |
| equal | 1153.766 | 54.587 | 27.000 | 27.475 |
| get | 0.039 | 0.129 | 0.056 | 0.056 |
| row-copy | 0.061 | 0.384 | 0.073 | 0.079 |
| row-view | — | 0.236 | 0.047 | 0.048 |
| set | 0.046 | 0.131 | 0.066 | 0.067 |

## Optimization versus the initial C implementation

65,536 elements; matched operations only. Initial source commit: `bc57700`.
Nested construction is excluded because the initial NumPy baseline preflattened its input; the final runner corrects this.

| Structure | Bits | Layout | Method | Initial µs | Final µs | Initial/final |
| --- | ---: | --- | --- | ---: | ---: | ---: |
| 1d | 2 | packed | slice-copy | 80.408 | 0.232 | 346.5× |
| 1d | 2 | packed | equal | 105.757 | 0.464 | 228.0× |
| 1d | 2 | packed | count | 63.009 | 0.703 | 89.6× |
| 1d | 2 | packed | find | 28.606 | 1.482 | 19.3× |
| 1d | 2 | word-aligned | slice-copy | 81.597 | 0.223 | 366.0× |
| 1d | 2 | word-aligned | equal | 105.720 | 0.476 | 222.1× |
| 1d | 2 | word-aligned | count | 63.174 | 0.717 | 88.1× |
| 1d | 2 | word-aligned | find | 25.323 | 1.336 | 19.0× |
| matrix | 2 | packed | get | 0.223 | 0.054 | 4.2× |
| matrix | 2 | word-aligned | get | 0.224 | 0.056 | 4.0× |
| ragged | 2 | packed | get | 0.430 | 0.054 | 8.0× |
| ragged | 2 | word-aligned | get | 0.432 | 0.054 | 8.0× |
| 1d | 5 | packed | slice-copy | 78.634 | 0.448 | 175.6× |
| 1d | 5 | packed | equal | 164.810 | 1.091 | 151.0× |
| 1d | 5 | packed | count | 93.960 | 3.210 | 29.3× |
| 1d | 5 | packed | find | 150.878 | 12.352 | 12.2× |
| 1d | 5 | word-aligned | slice-copy | 84.343 | 0.674 | 125.1× |
| 1d | 5 | word-aligned | equal | 112.460 | 1.184 | 95.0× |
| 1d | 5 | word-aligned | count | 70.370 | 1.793 | 39.2× |
| 1d | 5 | word-aligned | find | 156.780 | 13.967 | 11.2× |
| matrix | 5 | packed | get | 0.223 | 0.055 | 4.1× |
| matrix | 5 | word-aligned | get | 0.224 | 0.057 | 3.9× |
| ragged | 5 | packed | get | 0.437 | 0.055 | 8.0× |
| ragged | 5 | word-aligned | get | 0.436 | 0.056 | 7.8× |
| 1d | 7 | packed | slice-copy | 80.970 | 0.601 | 134.7× |
| 1d | 7 | packed | equal | 168.250 | 1.553 | 108.4× |
| 1d | 7 | packed | count | 95.047 | 3.271 | 29.1× |
| 1d | 7 | packed | find | 131.645 | 15.366 | 8.6× |
| 1d | 7 | word-aligned | slice-copy | 81.896 | 0.856 | 95.7× |
| 1d | 7 | word-aligned | equal | 146.509 | 1.591 | 92.1× |
| 1d | 7 | word-aligned | count | 83.553 | 2.372 | 35.2× |
| 1d | 7 | word-aligned | find | 132.121 | 15.169 | 8.7× |
| matrix | 7 | packed | get | 0.224 | 0.055 | 4.1× |
| matrix | 7 | word-aligned | get | 0.224 | 0.055 | 4.0× |
| ragged | 7 | packed | get | 0.436 | 0.056 | 7.7× |
| ragged | 7 | word-aligned | get | 0.436 | 0.055 | 7.9× |

## Remaining optimization targets

- Packing construction has validation and conversion costs; bytes/str/NumPy construction can be faster.
- Single-item list access and Python iteration remain strong baselines; not every method wins.
- Word-aligned slices starting within a word require realignment when copied.
- Long needles use KMP with linear worst-case complexity; more pattern distributions and lengths need measurement.
- Skewed workloads, cold-cache scans, dense bit-width sweeps, and hardware-isolated measurements are not covered by this run.
