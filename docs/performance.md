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
- Nested construction uses the same Python rows for every implementation; NumPy ragged includes flattening and offsets construction.
- Retained size counts owned buffers, object headers, shared objects once, and allocations kept alive by views. It is not RSS.
- Additional peak bytes are measured separately with tracemalloc: PyMem and NumPy-tracked allocations are included; untracked system allocations are excluded.
- View creation and copying are separate methods. An array view retains its full root allocation.

Raw results: [small/medium](results/m1-pro.json), [large](results/m1-pro-large.json), [initial baseline](results/m1-pro-baseline.json).
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
| construct | 3.031 | 0.197 | 0.149 | 0.505 | 0.450 | 0.443 |
| count | 8.624 | 0.390 | 0.396 | 0.817 | 0.064 | 0.061 |
| equal | 0.709 | 0.059 | 0.058 | 1.029 | 0.042 | 0.041 |
| find | 3.784 | 0.342 | 0.377 | 0.407 | 0.650 | 0.594 |
| gather | 3.341 | 5.425 | 5.283 | 0.311 | 2.000 | 1.970 |
| get | 0.034 | 0.041 | 0.045 | 0.058 | 0.043 | 0.043 |
| iterate-sum | 2.439 | 2.569 | 10.040 | 28.249 | 4.671 | 4.683 |
| random-get-sum | 8.011 | 9.805 | 8.189 | 17.344 | 10.145 | 10.168 |
| set | 0.044 | — | — | 0.069 | 0.055 | 0.055 |
| slice-copy | 0.738 | 0.092 | 0.098 | 0.254 | 0.091 | 0.094 |
| slice-view | — | — | — | 0.095 | 0.061 | 0.060 |

### 1d, 1,024 elements, 5 bits

| Method | python-list | python-bytes | python-str | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| construct | 3.083 | 0.198 | 0.149 | 0.500 | 0.507 | 0.467 |
| count | 9.292 | 0.383 | 0.391 | 0.817 | 0.103 | 0.083 |
| equal | 0.708 | 0.059 | 0.058 | 1.032 | 0.052 | 0.066 |
| find | 3.798 | 0.374 | 0.407 | 0.438 | 0.332 | 0.345 |
| gather | 3.387 | 5.480 | 5.435 | 0.311 | 2.110 | 2.051 |
| get | 0.034 | 0.041 | 0.045 | 0.058 | 0.045 | 0.044 |
| iterate-sum | 2.477 | 2.574 | 10.017 | 28.261 | 5.498 | 4.669 |
| random-get-sum | 8.006 | 9.799 | 8.207 | 17.366 | 10.463 | 10.259 |
| set | 0.044 | — | — | 0.069 | 0.054 | 0.055 |
| slice-copy | 0.739 | 0.092 | 0.098 | 0.255 | 0.095 | 0.174 |
| slice-view | — | — | — | 0.096 | 0.060 | 0.060 |

### 1d, 1,024 elements, 7 bits

| Method | python-list | python-bytes | python-str | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| construct | 3.097 | 0.199 | 0.149 | 0.502 | 0.547 | 0.487 |
| count | 9.254 | 0.383 | 0.398 | 0.814 | 0.102 | 0.092 |
| equal | 0.708 | 0.062 | 0.058 | 1.035 | 0.057 | 0.080 |
| find | 3.808 | 0.386 | 0.418 | 0.451 | 0.329 | 0.338 |
| gather | 3.304 | 5.339 | 5.308 | 0.311 | 2.138 | 2.076 |
| get | 0.034 | 0.040 | 0.046 | 0.060 | 0.044 | 0.045 |
| iterate-sum | 2.466 | 2.575 | 10.116 | 28.416 | 5.704 | 4.995 |
| random-get-sum | 8.007 | 9.752 | 8.179 | 17.330 | 10.504 | 10.303 |
| set | 0.044 | — | — | 0.069 | 0.055 | 0.055 |
| slice-copy | 0.752 | 0.093 | 0.097 | 0.255 | 0.098 | 0.199 |
| slice-view | — | — | — | 0.097 | 0.060 | 0.060 |

### 1d, 65,536 elements, 2 bits

| Method | python-list | python-bytes | python-str | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| construct | 196.312 | 4.243 | 3.492 | 1.693 | 14.351 | 14.254 |
| count | 581.760 | 20.385 | 20.590 | 4.763 | 0.716 | 0.719 |
| equal | 41.578 | 1.841 | 1.808 | 4.176 | 0.472 | 0.479 |
| find | 220.133 | 4.365 | 4.364 | 5.370 | 3.714 | 3.271 |
| gather | 3.442 | 5.173 | 5.318 | 0.312 | 1.683 | 1.685 |
| get | 0.034 | 0.040 | 0.045 | 0.059 | 0.043 | 0.044 |
| iterate-sum | 154.842 | 158.897 | 640.911 | 1793.021 | 290.475 | 290.316 |
| random-get-sum | 7.319 | 9.184 | 7.630 | 16.129 | 9.550 | 9.542 |
| set | 0.044 | — | — | 0.069 | 0.055 | 0.055 |
| slice-copy | 41.771 | 0.507 | 0.540 | 0.845 | 0.318 | 0.308 |
| slice-view | — | — | — | 0.096 | 0.060 | 0.060 |

### 1d, 65,536 elements, 5 bits

| Method | python-list | python-bytes | python-str | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| construct | 198.230 | 4.203 | 3.491 | 1.348 | 17.979 | 14.583 |
| count | 596.146 | 20.704 | 20.875 | 4.748 | 3.274 | 1.793 |
| equal | 41.639 | 1.850 | 1.853 | 4.127 | 1.102 | 1.183 |
| find | 242.908 | 27.506 | 27.595 | 29.233 | 15.289 | 15.685 |
| gather | 3.453 | 5.324 | 5.274 | 0.311 | 1.979 | 1.744 |
| get | 0.034 | 0.040 | 0.046 | 0.058 | 0.045 | 0.045 |
| iterate-sum | 156.219 | 159.026 | 648.146 | 1781.729 | 343.901 | 292.228 |
| random-get-sum | 7.287 | 9.168 | 7.676 | 16.122 | 9.750 | 9.591 |
| set | 0.044 | — | — | 0.069 | 0.055 | 0.055 |
| slice-copy | 41.326 | 0.509 | 0.560 | 0.829 | 0.651 | 4.686 |
| slice-view | — | — | — | 0.096 | 0.061 | 0.060 |

### 1d, 65,536 elements, 7 bits

| Method | python-list | python-bytes | python-str | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| construct | 199.158 | 4.371 | 3.900 | 1.389 | 20.467 | 15.155 |
| count | 589.018 | 20.777 | 20.425 | 4.785 | 3.275 | 2.376 |
| equal | 48.072 | 1.817 | 1.809 | 4.164 | 1.552 | 1.601 |
| find | 242.667 | 26.632 | 26.620 | 28.330 | 13.315 | 14.311 |
| gather | 3.417 | 5.204 | 5.296 | 0.311 | 2.096 | 1.813 |
| get | 0.034 | 0.041 | 0.047 | 0.059 | 0.044 | 0.045 |
| iterate-sum | 156.015 | 159.251 | 640.047 | 1784.677 | 355.393 | 310.832 |
| random-get-sum | 7.320 | 9.145 | 7.622 | 16.129 | 9.822 | 9.664 |
| set | 0.044 | — | — | 0.069 | 0.055 | 0.055 |
| slice-copy | 41.057 | 0.509 | 0.721 | 0.802 | 0.854 | 6.214 |
| slice-view | — | — | — | 0.096 | 0.060 | 0.060 |

### 1d, 1,048,576 elements, 2 bits

| Method | python-list | python-bytes | python-str | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| construct | 3182.521 | 45.820 | 59.452 | 19.415 | 238.345 | 227.471 |
| count | 9446.959 | 339.948 | 328.982 | 64.624 | 10.548 | 10.563 |
| equal | 784.464 | 27.420 | 27.334 | 48.111 | 6.714 | 6.671 |
| find | 3530.604 | 73.110 | 74.781 | 94.013 | 72.210 | 69.600 |
| gather | 3.474 | 5.216 | 5.323 | 0.311 | 1.653 | 1.654 |
| get | 0.034 | 0.041 | 0.046 | 0.058 | 0.044 | 0.044 |
| iterate-sum | 2564.604 | 2543.584 | 10175.916 | 29101.917 | 4648.896 | 4637.770 |
| random-get-sum | 7.386 | 9.150 | 7.658 | 16.267 | 9.488 | 9.476 |
| set | 0.044 | — | — | 0.070 | 0.055 | 0.055 |
| slice-copy | 668.250 | 9.326 | 8.800 | 9.506 | 3.848 | 3.859 |
| slice-view | — | — | — | 0.097 | 0.061 | 0.060 |

### 1d, 1,048,576 elements, 5 bits

| Method | python-list | python-bytes | python-str | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| construct | 3207.938 | 46.649 | 59.244 | 19.077 | 277.897 | 222.971 |
| count | 9510.292 | 334.737 | 343.151 | 60.830 | 51.622 | 27.898 |
| equal | 689.641 | 27.443 | 27.249 | 49.549 | 17.214 | 17.842 |
| find | 3920.062 | 443.305 | 441.229 | 466.841 | 578.141 | 576.740 |
| gather | 3.488 | 5.369 | 5.326 | 0.311 | 1.916 | 1.737 |
| get | 0.034 | 0.041 | 0.046 | 0.059 | 0.044 | 0.044 |
| iterate-sum | 2528.875 | 2574.458 | 10148.834 | 28680.041 | 5740.375 | 4638.667 |
| random-get-sum | 7.407 | 9.196 | 7.664 | 16.104 | 9.713 | 9.656 |
| set | 0.044 | — | — | 0.069 | 0.055 | 0.055 |
| slice-copy | 669.396 | 9.402 | 8.496 | 9.497 | 8.762 | 71.225 |
| slice-view | — | — | — | 0.096 | 0.061 | 0.060 |

### 1d, 1,048,576 elements, 7 bits

| Method | python-list | python-bytes | python-str | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| construct | 3208.895 | 45.836 | 59.394 | 18.830 | 310.259 | 232.392 |
| count | 9461.958 | 334.109 | 346.628 | 63.799 | 52.259 | 37.185 |
| equal | 782.875 | 27.750 | 27.015 | 46.162 | 23.906 | 23.949 |
| find | 3880.937 | 423.076 | 422.979 | 442.560 | 266.509 | 264.762 |
| gather | 3.462 | 5.634 | 5.274 | 0.316 | 2.119 | 1.790 |
| get | 0.034 | 0.041 | 0.046 | 0.059 | 0.044 | 0.045 |
| iterate-sum | 2531.521 | 2650.167 | 10155.958 | 28730.333 | 5816.333 | 4972.646 |
| random-get-sum | 7.419 | 9.198 | 7.705 | 16.114 | 9.947 | 9.810 |
| set | 0.044 | — | — | 0.069 | 0.055 | 0.055 |
| slice-copy | 687.552 | 9.373 | 8.712 | 9.380 | 12.043 | 95.985 |
| slice-view | — | — | — | 0.096 | 0.061 | 0.061 |

### matrix, 1,024 elements, 2 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2.295 | 18.050 | 16.135 | 17.152 |
| count | 9.250 | 0.848 | 0.082 | 0.082 |
| equal | 0.934 | 1.047 | 0.046 | 0.046 |
| get | 0.038 | 0.083 | 0.054 | 0.054 |
| row-copy | 0.145 | 0.222 | 0.075 | 0.078 |
| row-view | — | 0.085 | 0.047 | 0.047 |
| set | 0.046 | 0.089 | 0.064 | 0.064 |

### matrix, 1,024 elements, 5 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2.271 | 18.076 | 16.826 | 16.390 |
| count | 10.044 | 0.842 | 0.109 | 0.087 |
| equal | 0.953 | 1.045 | 0.058 | 0.070 |
| get | 0.038 | 0.084 | 0.055 | 0.056 |
| row-copy | 0.144 | 0.220 | 0.080 | 0.092 |
| row-view | — | 0.082 | 0.047 | 0.047 |
| set | 0.045 | 0.089 | 0.065 | 0.065 |

### matrix, 1,024 elements, 7 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2.262 | 18.066 | 16.922 | 16.456 |
| count | 9.880 | 0.841 | 0.109 | 0.097 |
| equal | 0.933 | 1.044 | 0.065 | 0.085 |
| get | 0.039 | 0.083 | 0.055 | 0.056 |
| row-copy | 0.146 | 0.220 | 0.080 | 0.087 |
| row-view | — | 0.083 | 0.047 | 0.047 |
| set | 0.045 | 0.088 | 0.065 | 0.065 |

### matrix, 65,536 elements, 2 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 140.565 | 1139.719 | 835.823 | 835.797 |
| count | 619.990 | 4.824 | 0.724 | 0.723 |
| equal | 60.562 | 4.214 | 0.540 | 0.548 |
| get | 0.038 | 0.084 | 0.054 | 0.055 |
| row-copy | 0.146 | 0.222 | 0.077 | 0.080 |
| row-view | — | 0.084 | 0.048 | 0.047 |
| set | 0.045 | 0.089 | 0.065 | 0.066 |

### matrix, 65,536 elements, 5 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 142.807 | 1138.938 | 860.682 | 841.745 |
| count | 627.260 | 4.808 | 3.280 | 1.830 |
| equal | 59.267 | 4.233 | 1.277 | 1.325 |
| get | 0.040 | 0.083 | 0.056 | 0.056 |
| row-copy | 0.148 | 0.222 | 0.081 | 0.093 |
| row-view | — | 0.084 | 0.048 | 0.047 |
| set | 0.046 | 0.089 | 0.066 | 0.066 |

### matrix, 65,536 elements, 7 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 141.938 | 1138.859 | 875.365 | 829.849 |
| count | 624.792 | 4.841 | 3.282 | 2.380 |
| equal | 58.768 | 4.244 | 1.789 | 1.844 |
| get | 0.039 | 0.083 | 0.055 | 0.055 |
| row-copy | 0.149 | 0.222 | 0.081 | 0.088 |
| row-view | — | 0.084 | 0.047 | 0.047 |
| set | 0.046 | 0.089 | 0.066 | 0.066 |

### matrix, 1,048,576 elements, 2 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2751.479 | 18257.666 | 15490.375 | 15301.083 |
| count | 9882.250 | 64.182 | 10.543 | 10.544 |
| equal | 974.297 | 47.645 | 7.952 | 7.738 |
| get | 0.039 | 0.084 | 0.055 | 0.055 |
| row-copy | 0.146 | 0.221 | 0.077 | 0.079 |
| row-view | — | 0.083 | 0.047 | 0.047 |
| set | 0.046 | 0.089 | 0.066 | 0.066 |

### matrix, 1,048,576 elements, 5 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2820.500 | 18337.709 | 14868.791 | 14361.542 |
| count | 10031.833 | 63.736 | 51.696 | 27.903 |
| equal | 985.438 | 43.106 | 19.632 | 19.562 |
| get | 0.039 | 0.083 | 0.056 | 0.055 |
| row-copy | 0.146 | 0.221 | 0.080 | 0.091 |
| row-view | — | 0.083 | 0.047 | 0.047 |
| set | 0.046 | 0.089 | 0.066 | 0.067 |

### matrix, 1,048,576 elements, 7 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2914.854 | 18330.708 | 17226.666 | 16077.292 |
| count | 10045.750 | 64.098 | 51.658 | 37.153 |
| equal | 978.552 | 49.437 | 27.486 | 27.844 |
| get | 0.040 | 0.083 | 0.056 | 0.055 |
| row-copy | 0.146 | 0.221 | 0.080 | 0.087 |
| row-view | — | 0.084 | 0.048 | 0.048 |
| set | 0.046 | 0.089 | 0.066 | 0.066 |

### ragged, 1,024 elements, 2 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2.652 | 28.427 | 16.522 | 16.470 |
| count | 9.307 | 0.827 | 0.083 | 0.083 |
| equal | 0.936 | 2.240 | 0.048 | 0.049 |
| get | 0.039 | 0.122 | 0.056 | 0.056 |
| row-copy | 0.141 | 0.390 | 0.075 | 0.146 |
| row-view | — | 0.240 | 0.047 | 0.047 |
| set | 0.044 | 0.129 | 0.065 | 0.065 |

### ragged, 1,024 elements, 5 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2.600 | 28.378 | 16.810 | 16.480 |
| count | 9.937 | 0.825 | 0.109 | 0.089 |
| equal | 0.937 | 2.246 | 0.059 | 0.072 |
| get | 0.039 | 0.122 | 0.056 | 0.056 |
| row-copy | 0.075 | 0.392 | 0.076 | 0.093 |
| row-view | — | 0.237 | 0.047 | 0.047 |
| set | 0.045 | 0.129 | 0.065 | 0.064 |

### ragged, 1,024 elements, 7 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2.747 | 28.466 | 17.306 | 16.613 |
| count | 9.966 | 0.824 | 0.109 | 0.097 |
| equal | 0.956 | 2.248 | 0.065 | 0.086 |
| get | 0.038 | 0.122 | 0.056 | 0.056 |
| row-copy | 0.186 | 0.384 | 0.083 | 0.090 |
| row-view | — | 0.244 | 0.047 | 0.047 |
| set | 0.044 | 0.129 | 0.065 | 0.064 |

### ragged, 65,536 elements, 2 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 171.073 | 1674.958 | 869.031 | 867.688 |
| count | 612.729 | 4.744 | 0.723 | 0.723 |
| equal | 61.237 | 5.835 | 0.728 | 0.734 |
| get | 0.039 | 0.124 | 0.055 | 0.054 |
| row-copy | 0.225 | 0.385 | 0.079 | 0.093 |
| row-view | — | 0.237 | 0.048 | 0.048 |
| set | 0.047 | 0.132 | 0.065 | 0.066 |

### ragged, 65,536 elements, 5 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 171.003 | 1670.198 | 905.865 | 867.271 |
| count | 628.833 | 4.793 | 3.276 | 1.801 |
| equal | 61.301 | 5.903 | 1.377 | 1.461 |
| get | 0.040 | 0.124 | 0.055 | 0.056 |
| row-copy | 0.207 | 0.393 | 0.082 | 0.098 |
| row-view | — | 0.241 | 0.047 | 0.048 |
| set | 0.046 | 0.131 | 0.066 | 0.065 |

### ragged, 65,536 elements, 7 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 171.862 | 1672.094 | 914.495 | 863.906 |
| count | 625.880 | 4.788 | 3.280 | 2.377 |
| equal | 60.035 | 5.860 | 1.792 | 1.826 |
| get | 0.040 | 0.126 | 0.056 | 0.056 |
| row-copy | 0.219 | 0.384 | 0.086 | 0.091 |
| row-view | — | 0.238 | 0.048 | 0.047 |
| set | 0.046 | 0.131 | 0.065 | 0.065 |

### ragged, 1,048,576 elements, 2 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2907.063 | 26672.625 | 15063.750 | 14965.708 |
| count | 9904.417 | 64.048 | 10.567 | 10.548 |
| equal | 1078.724 | 47.185 | 10.627 | 10.631 |
| get | 0.039 | 0.124 | 0.055 | 0.055 |
| row-copy | 0.219 | 0.386 | 0.078 | 0.083 |
| row-view | — | 0.238 | 0.048 | 0.048 |
| set | 0.046 | 0.131 | 0.066 | 0.066 |

### ragged, 1,048,576 elements, 5 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2864.271 | 26674.500 | 15704.958 | 15437.834 |
| count | 10080.542 | 64.012 | 51.688 | 27.900 |
| equal | 1102.875 | 54.592 | 20.833 | 21.749 |
| get | 0.039 | 0.124 | 0.056 | 0.056 |
| row-copy | 0.111 | 0.390 | 0.078 | 0.079 |
| row-view | — | 0.237 | 0.047 | 0.048 |
| set | 0.046 | 0.130 | 0.066 | 0.066 |

### ragged, 1,048,576 elements, 7 bits

| Method | python-list | numpy | packed | word-aligned |
| --- | ---: | ---: | ---: | ---: |
| construct | 2859.041 | 26726.958 | 17647.417 | 16506.667 |
| count | 10012.375 | 63.984 | 51.643 | 37.343 |
| equal | 1125.391 | 47.358 | 26.821 | 27.533 |
| get | 0.039 | 0.124 | 0.056 | 0.057 |
| row-copy | 0.060 | 0.384 | 0.074 | 0.079 |
| row-view | — | 0.237 | 0.048 | 0.048 |
| set | 0.046 | 0.131 | 0.068 | 0.067 |

## Optimization versus the initial C implementation

65,536 elements; matched operations only. Initial source commit: `bc57700`.
Nested construction is excluded because the initial NumPy baseline preflattened its input; the final runner corrects this.

| Structure | Bits | Layout | Method | Initial µs | Final µs | Initial/final |
| --- | ---: | --- | --- | ---: | ---: | ---: |
| 1d | 2 | packed | slice-copy | 80.408 | 0.318 | 253.0× |
| 1d | 2 | packed | equal | 105.757 | 0.472 | 224.0× |
| 1d | 2 | packed | count | 63.009 | 0.716 | 87.9× |
| 1d | 2 | packed | find | 28.606 | 3.714 | 7.7× |
| 1d | 2 | word-aligned | slice-copy | 81.597 | 0.308 | 265.4× |
| 1d | 2 | word-aligned | equal | 105.720 | 0.479 | 220.5× |
| 1d | 2 | word-aligned | count | 63.174 | 0.719 | 87.8× |
| 1d | 2 | word-aligned | find | 25.323 | 3.271 | 7.7× |
| matrix | 2 | packed | get | 0.223 | 0.054 | 4.1× |
| matrix | 2 | word-aligned | get | 0.224 | 0.055 | 4.1× |
| ragged | 2 | packed | get | 0.430 | 0.055 | 7.8× |
| ragged | 2 | word-aligned | get | 0.432 | 0.054 | 8.0× |
| 1d | 5 | packed | slice-copy | 78.634 | 0.651 | 120.8× |
| 1d | 5 | packed | equal | 164.810 | 1.102 | 149.6× |
| 1d | 5 | packed | count | 93.960 | 3.274 | 28.7× |
| 1d | 5 | packed | find | 150.878 | 15.289 | 9.9× |
| 1d | 5 | word-aligned | slice-copy | 84.343 | 4.686 | 18.0× |
| 1d | 5 | word-aligned | equal | 112.460 | 1.183 | 95.0× |
| 1d | 5 | word-aligned | count | 70.370 | 1.793 | 39.2× |
| 1d | 5 | word-aligned | find | 156.780 | 15.685 | 10.0× |
| matrix | 5 | packed | get | 0.223 | 0.056 | 4.0× |
| matrix | 5 | word-aligned | get | 0.224 | 0.056 | 4.0× |
| ragged | 5 | packed | get | 0.437 | 0.055 | 7.9× |
| ragged | 5 | word-aligned | get | 0.436 | 0.056 | 7.8× |
| 1d | 7 | packed | slice-copy | 80.970 | 0.854 | 94.8× |
| 1d | 7 | packed | equal | 168.250 | 1.552 | 108.4× |
| 1d | 7 | packed | count | 95.047 | 3.275 | 29.0× |
| 1d | 7 | packed | find | 131.645 | 13.315 | 9.9× |
| 1d | 7 | word-aligned | slice-copy | 81.896 | 6.214 | 13.2× |
| 1d | 7 | word-aligned | equal | 146.509 | 1.601 | 91.5× |
| 1d | 7 | word-aligned | count | 83.553 | 2.376 | 35.2× |
| 1d | 7 | word-aligned | find | 132.121 | 14.311 | 9.2× |
| matrix | 7 | packed | get | 0.224 | 0.055 | 4.1× |
| matrix | 7 | word-aligned | get | 0.224 | 0.055 | 4.0× |
| ragged | 7 | packed | get | 0.436 | 0.056 | 7.8× |
| ragged | 7 | word-aligned | get | 0.436 | 0.056 | 7.7× |

## Remaining optimization targets

- Packing construction has validation and conversion costs; bytes/str/NumPy construction can be faster.
- Single-item list access and Python iteration remain strong baselines; not every method wins.
- Word-aligned slices starting within a word require realignment when copied.
- Long needles use KMP with linear worst-case complexity; more pattern distributions and lengths need measurement.
- Skewed workloads, cold-cache scans, dense bit-width sweeps, and hardware-isolated measurements are not covered by this run.
