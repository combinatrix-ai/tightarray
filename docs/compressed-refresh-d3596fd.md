# Broad production comparison at d3596fd

This is a same-run snapshot of production commit `d3596fd9899797f9e1dede772fbc1fb03300d9bd`, after native palette packing. It does not establish a before/after speedup over historical runs. Experimental compression-context pools are excluded.

## Findings

- General superiority over Blosc2 is **not established**. At 4 KiB chunks, adaptive ZSTD on local-two takes 110.638 ms to construct versus 4.947 ms for dense ZSTD (22.4x); updates plus flush take 23.837 versus 1.591 ms (15.0x). Multiple codec attempts remain a major target.
- Default codec-free storage is much cheaper to build/update than adaptive ZSTD, with approximately the same cold retained sizes in the six default configurations. In local-two it retains 143,273 bytes versus dense ZSTD's 257,408 bytes, and global reads take 0.267 versus 1.191 ms. This is workload-specific, not a universal advantage.
- Codec selection cannot simply be disabled without a size tradeoff: with 16 KiB chunks spanning four different local-two regions, codec-free storage retains 397,054 bytes versus adaptive ZSTD's 196,611 bytes. However, adaptive ZSTD construction is 110.224 ms versus dense ZSTD's 3.917 ms, and updates plus flush are 108.027 versus 4.375 ms. Even reads lose in this configuration.
- Plain packed storage is a strong baseline where a global width suffices: random8 uses 393,288 retained bytes and global reads take 0.013 ms, versus codec-free adaptive storage's 405,033 bytes and 0.442 ms. NumPy builds this input in 0.027 ms but retains 1,048,688 bytes. Adaptive chunking has a real cost.
- Next exact-policy experiment: remove temporary candidate objects, list snapshots, and repeated selection dispatch while preserving all codec inputs, attempt order, strict tie behavior and final records. This will not by itself remove repeated codec work.

## Method and limitations

CPython 3.12.8, NumPy 2.5.3, Python-Blosc2 4.13.1, ARM64. Each configuration contains 1,048,576 logical uint8 elements, with five trials and rotated backend order. Six datasets at 4 KiB chunks / 64 KiB cache, four chunk-size variations, and two zero-cache variations give 12 configurations x seven backends = 84 rows. `random8` means eight values (3 bits), and `random32` means 32 values (5 bits), not 8-bit/32-bit random integers. Local-two input regions stay 4 KiB across the chunk-size sweep.

Times below are medians in milliseconds. Scalar operations each perform 256 reads; local/medium working sets are prewarmed. Block reads perform 64 reads of 64 bytes. Updates perform 64 scalar assignments followed by flush, choosing from the observed alphabet; some assignments may leave a value unchanged. This is not an all-changed bulk-write benchmark. Correctness checks occur outside timed regions, including reading after clearing caches.

Dense Blosc2 uses the benchmark's custom decoded uint8 LRU with dirty writeback, one compression thread, level 5, BITSHUFFLE and typesize 1. It is not a benchmark of every Blosc2 NDArray API; the dense helper also performs less input validation. Adaptive methods include their Python API and representation selection. The cache budget measures retained decoded payload, not a process memory limit.

`Cold owned B` is the median initial `sys.getsizeof` retained-graph estimate, including metadata but excluding shared runtime, transient scratch and allocator capacity. It is **not RSS**. Individual samples also preserve stored/cache payload bytes and cache counters. Uniform chunks may have zero payload while retaining nonzero metadata.

All 84 rows passed exact operation checks. Python/C/header/native-binary hashes were checked before and after the run and are included in the [lossless raw artifact](compressed-refresh-d3596fd-results.json.gz). The refresh wrapper itself is also hashed. No production changes occurred during measurement.

Reproduce:

```sh
python -m benchmarks.compressed_refresh --repeats 5 --output /tmp/compressed-refresh.json.gz
```

## Complete results

### random8 — chunk 4096 B, cache 65536 B

| Backend | Cold owned B | Build | Local | Medium | Global | Read64 | Update + flush |
|---|---:|---:|---:|---:|---:|---:|---:|
| numpy | 1048688 | 0.027 | 0.021 | 0.018 | 0.022 | 0.012 | 0.005 |
| packed | 393288 | 0.153 | 0.013 | 0.013 | 0.013 | 0.008 | 0.003 |
| palette-none | 404985 | 1.810 | 0.079 | 0.077 | 0.442 | 0.128 | 0.497 |
| palette-lz4 | 404976 | 6.187 | 0.077 | 0.075 | 0.415 | 0.119 | 1.367 |
| palette-zstd | 404969 | 10.172 | 0.076 | 0.074 | 0.420 | 0.123 | 2.215 |
| dense-lz4 | 423291 | 2.520 | 0.073 | 0.665 | 1.187 | 0.309 | 0.918 |
| dense-zstd | 420211 | 4.898 | 0.070 | 0.711 | 1.214 | 0.366 | 1.509 |

### random32 — chunk 4096 B, cache 65536 B

| Backend | Cold owned B | Build | Local | Medium | Global | Read64 | Update + flush |
|---|---:|---:|---:|---:|---:|---:|---:|
| numpy | 1048688 | 0.030 | 0.022 | 0.018 | 0.025 | 0.014 | 0.005 |
| packed | 655432 | 0.159 | 0.012 | 0.012 | 0.012 | 0.010 | 0.003 |
| palette-none | 667049 | 1.723 | 0.080 | 0.185 | 0.453 | 0.138 | 0.572 |
| palette-lz4 | 667048 | 5.982 | 0.077 | 0.189 | 0.573 | 0.153 | 1.559 |
| palette-zstd | 667049 | 11.538 | 0.075 | 0.182 | 0.455 | 0.135 | 2.794 |
| dense-lz4 | 686123 | 2.721 | 0.070 | 0.742 | 1.263 | 0.309 | 0.953 |
| dense-zstd | 682275 | 5.475 | 0.068 | 0.675 | 1.191 | 0.321 | 1.739 |

### local-two — chunk 4096 B, cache 65536 B

| Backend | Cold owned B | Build | Local | Medium | Global | Read64 | Update + flush |
|---|---:|---:|---:|---:|---:|---:|---:|
| numpy | 1048688 | 0.029 | 0.022 | 0.019 | 0.022 | 0.012 | 0.005 |
| packed | 1048648 | 0.047 | 0.011 | 0.011 | 0.014 | 0.009 | 0.004 |
| palette-none | 143273 | 2.708 | 0.079 | 0.077 | 0.267 | 0.106 | 1.351 |
| palette-lz4 | 143272 | 10.752 | 0.079 | 0.074 | 0.289 | 0.121 | 3.013 |
| palette-zstd | 143273 | 110.638 | 0.076 | 0.073 | 0.271 | 0.108 | 23.837 |
| dense-lz4 | 259403 | 2.583 | 0.069 | 0.634 | 1.164 | 0.302 | 1.135 |
| dense-zstd | 257408 | 4.947 | 0.068 | 0.681 | 1.191 | 0.327 | 1.591 |

### uniform-chunks — chunk 4096 B, cache 65536 B

| Backend | Cold owned B | Build | Local | Medium | Global | Read64 | Update + flush |
|---|---:|---:|---:|---:|---:|---:|---:|
| numpy | 1048688 | 0.028 | 0.021 | 0.018 | 0.021 | 0.012 | 0.004 |
| packed | 1048648 | 0.046 | 0.011 | 0.011 | 0.014 | 0.009 | 0.003 |
| palette-none | 7209 | 0.310 | 0.060 | 0.059 | 0.056 | 0.044 | 0.963 |
| palette-lz4 | 7208 | 0.310 | 0.066 | 0.056 | 0.055 | 0.047 | 1.162 |
| palette-zstd | 7209 | 0.298 | 0.057 | 0.055 | 0.056 | 0.043 | 1.155 |
| dense-lz4 | 31741 | 2.565 | 0.067 | 0.616 | 1.040 | 0.307 | 0.897 |
| dense-zstd | 29231 | 3.387 | 0.068 | 0.715 | 1.267 | 0.366 | 1.484 |

### runs32 — chunk 4096 B, cache 65536 B

| Backend | Cold owned B | Build | Local | Medium | Global | Read64 | Update + flush |
|---|---:|---:|---:|---:|---:|---:|---:|
| numpy | 1048688 | 0.029 | 0.021 | 0.018 | 0.022 | 0.012 | 0.004 |
| packed | 655432 | 0.149 | 0.012 | 0.011 | 0.012 | 0.009 | 0.003 |
| palette-none | 75171 | 1.258 | 0.080 | 0.289 | 0.866 | 0.236 | 0.510 |
| palette-lz4 | 75170 | 7.779 | 0.081 | 0.285 | 0.857 | 0.227 | 1.912 |
| palette-zstd | 75171 | 76.307 | 0.076 | 0.282 | 0.813 | 0.226 | 16.860 |
| dense-lz4 | 278016 | 3.618 | 0.068 | 0.791 | 1.502 | 0.405 | 1.209 |
| dense-zstd | 80001 | 42.306 | 0.070 | 0.895 | 1.845 | 0.451 | 10.387 |

### rare-spikes — chunk 4096 B, cache 65536 B

| Backend | Cold owned B | Build | Local | Medium | Global | Read64 | Update + flush |
|---|---:|---:|---:|---:|---:|---:|---:|
| numpy | 1048688 | 0.027 | 0.019 | 0.018 | 0.021 | 0.011 | 0.004 |
| packed | 1048648 | 0.046 | 0.011 | 0.011 | 0.013 | 0.009 | 0.003 |
| palette-none | 18536 | 1.495 | 0.081 | 0.077 | 0.537 | 0.158 | 0.986 |
| palette-lz4 | 18535 | 7.996 | 0.077 | 0.074 | 0.524 | 0.161 | 2.520 |
| palette-zstd | 18536 | 12.309 | 0.076 | 0.074 | 0.522 | 0.152 | 3.600 |
| dense-lz4 | 46771 | 2.547 | 0.072 | 0.682 | 1.209 | 0.319 | 0.937 |
| dense-zstd | 37746 | 5.102 | 0.066 | 0.681 | 1.212 | 0.332 | 1.662 |

### random8 — chunk 1024 B, cache 65536 B

| Backend | Cold owned B | Build | Local | Medium | Global | Read64 | Update + flush |
|---|---:|---:|---:|---:|---:|---:|---:|
| numpy | 1048688 | 0.029 | 0.022 | 0.018 | 0.023 | 0.012 | 0.006 |
| packed | 393288 | 0.165 | 0.013 | 0.013 | 0.013 | 0.009 | 0.003 |
| palette-none | 438441 | 4.450 | 0.093 | 0.085 | 0.330 | 0.120 | 0.378 |
| palette-lz4 | 438440 | 18.723 | 0.088 | 0.089 | 0.349 | 0.126 | 1.351 |
| palette-zstd | 438441 | 27.552 | 0.089 | 0.082 | 0.345 | 0.132 | 1.840 |
| dense-lz4 | 497929 | 8.630 | 0.078 | 0.084 | 0.724 | 0.205 | 0.676 |
| dense-zstd | 497929 | 12.904 | 0.084 | 0.087 | 0.738 | 0.217 | 0.952 |

### random8 — chunk 16384 B, cache 65536 B

| Backend | Cold owned B | Build | Local | Medium | Global | Read64 | Update + flush |
|---|---:|---:|---:|---:|---:|---:|---:|
| numpy | 1048688 | 0.029 | 0.023 | 0.018 | 0.023 | 0.013 | 0.006 |
| packed | 393288 | 0.152 | 0.014 | 0.012 | 0.013 | 0.008 | 0.003 |
| palette-none | 396553 | 1.014 | 0.086 | 0.385 | 0.440 | 0.145 | 1.211 |
| palette-lz4 | 396552 | 2.618 | 0.080 | 0.371 | 0.482 | 0.164 | 2.425 |
| palette-zstd | 396553 | 5.038 | 0.079 | 0.368 | 0.461 | 0.148 | 4.329 |
| dense-lz4 | 404843 | 1.100 | 1.872 | 2.993 | 3.337 | 0.895 | 1.872 |
| dense-zstd | 400491 | 2.560 | 1.820 | 2.989 | 3.408 | 0.885 | 2.909 |

### local-two — chunk 1024 B, cache 65536 B

| Backend | Cold owned B | Build | Local | Medium | Global | Read64 | Update + flush |
|---|---:|---:|---:|---:|---:|---:|---:|
| numpy | 1048688 | 0.031 | 0.021 | 0.018 | 0.024 | 0.014 | 0.005 |
| packed | 1048648 | 0.046 | 0.014 | 0.011 | 0.016 | 0.012 | 0.006 |
| palette-none | 178345 | 6.787 | 0.089 | 0.086 | 0.273 | 0.118 | 0.789 |
| palette-lz4 | 178344 | 30.363 | 0.084 | 0.085 | 0.273 | 0.118 | 2.182 |
| palette-zstd | 178345 | 108.668 | 0.089 | 0.081 | 0.272 | 0.118 | 7.488 |
| dense-lz4 | 406974 | 8.436 | 0.079 | 0.078 | 0.734 | 0.215 | 0.702 |
| dense-zstd | 344537 | 12.890 | 0.077 | 0.085 | 0.731 | 0.217 | 1.030 |

### local-two — chunk 16384 B, cache 65536 B

| Backend | Cold owned B | Build | Local | Medium | Global | Read64 | Update + flush |
|---|---:|---:|---:|---:|---:|---:|---:|
| numpy | 1048688 | 0.033 | 0.024 | 0.018 | 0.022 | 0.012 | 0.004 |
| packed | 1048648 | 0.049 | 0.011 | 0.011 | 0.013 | 0.008 | 0.003 |
| palette-none | 397054 | 2.682 | 0.084 | 0.398 | 0.437 | 0.151 | 4.793 |
| palette-lz4 | 241984 | 6.943 | 1.752 | 2.977 | 3.329 | 0.859 | 8.207 |
| palette-zstd | 196611 | 110.224 | 2.179 | 4.023 | 4.338 | 1.114 | 108.027 |
| dense-lz4 | 241956 | 1.262 | 1.438 | 2.656 | 2.656 | 0.820 | 1.762 |
| dense-zstd | 238092 | 3.917 | 1.706 | 2.896 | 3.154 | 0.935 | 4.375 |

### random8 — chunk 4096 B, cache 0 B

| Backend | Cold owned B | Build | Local | Medium | Global | Read64 | Update + flush |
|---|---:|---:|---:|---:|---:|---:|---:|
| numpy | 1048688 | 0.027 | 0.020 | 0.018 | 0.024 | 0.013 | 0.005 |
| packed | 393288 | 0.157 | 0.015 | 0.013 | 0.014 | 0.011 | 0.004 |
| palette-none | 404877 | 1.819 | 0.253 | 0.241 | 0.252 | 0.099 | 0.767 |
| palette-lz4 | 404876 | 6.317 | 0.239 | 0.237 | 0.246 | 0.095 | 1.973 |
| palette-zstd | 404877 | 10.235 | 0.252 | 0.250 | 0.266 | 0.105 | 3.348 |
| dense-lz4 | 423151 | 2.647 | 1.053 | 1.064 | 1.080 | 0.307 | 1.119 |
| dense-zstd | 420079 | 4.684 | 1.339 | 1.153 | 1.282 | 0.404 | 1.730 |

### uniform-chunks — chunk 4096 B, cache 0 B

| Backend | Cold owned B | Build | Local | Medium | Global | Read64 | Update + flush |
|---|---:|---:|---:|---:|---:|---:|---:|
| numpy | 1048688 | 0.034 | 0.021 | 0.019 | 0.025 | 0.013 | 0.005 |
| packed | 1048648 | 0.050 | 0.013 | 0.012 | 0.018 | 0.009 | 0.005 |
| palette-none | 7181 | 0.337 | 0.061 | 0.062 | 0.083 | 0.053 | 0.957 |
| palette-lz4 | 7180 | 0.310 | 0.057 | 0.055 | 0.055 | 0.043 | 1.201 |
| palette-zstd | 7181 | 0.317 | 0.058 | 0.055 | 0.055 | 0.045 | 1.545 |
| dense-lz4 | 31713 | 2.491 | 0.998 | 0.993 | 0.972 | 0.286 | 0.928 |
| dense-zstd | 29203 | 3.446 | 1.180 | 1.183 | 1.161 | 0.328 | 1.522 |

