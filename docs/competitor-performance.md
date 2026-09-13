# Competitor performance on Apple M1 Pro

All reported results passed reference checks before timing. Five timing samples per operation; median shown. Separate operations are not combined into a headline speedup.

Python 3.13.15; Darwin arm64. Source versions: numpy 2.5.3, bitarray 3.11.0, bitstring 4.4.0, bitformat 0.9.0, ml_dtypes 0.6.0, blosc2 4.13.0, bitstruct 8.23.0, cbitstruct 1.2.0, bpack 1.3.0, npstructures 0.2.19, intbitset 4.1.2, tightarray 0.1.0.dev0, tibs 0.5.7, numexpr 2.14.2.

## 65,536 elements, uniform 5-bit values

Values are identical across libraries. Payload excludes object headers and allocator overhead. Python list payload is its pointer array, excluding shared integer objects. Rust/C allocations may not be visible to tracemalloc. Shallow object size is not total retained memory.

| Library | Payload KiB | Construct ms | Get ns | Set/restore ns | Copy µs | Count µs | Gather 256 µs | Sum µs | Equals µs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| python-bytes | 64.00 | 0.197 | 36.636 | — | 3.956 | 53.706 | 6.675 | 173.008 | 1.933 |
| array-B | 64.00 | 0.825 | 39.939 | 81.302 | 0.916 | 486.281 | 7.061 | 187.650 | 20.600 |
| numpy-u8 | 64.00 | 1.027 | 64.022 | 126.101 | 1.063 | 4.852 | 0.331 | 13.635 | 4.106 |
| tightarray-packed | 40.00 | 0.431 | 39.789 | 73.060 | 0.735 | 3.286 | 0.364 | 348.193 | 1.112 |
| tightarray-aligned | 42.67 | 0.390 | 39.396 | 72.168 | 0.596 | 1.797 | 0.287 | 294.763 | 1.191 |
| tightarray-api | 40.00 | 8.399 | 12705.079 | 54774916.964 | 23.215 | 46.696 | 16.953 | 26.895 | 45.953 |
| bitstring | 40.00 | 166.492 | 1851.298 | 9142.987 | 4.572 | 100874.000 | 476.167 | 101312.042 | 1.386 |
| bitformat | 40.00 | 26.008 | 769.409 | 1948.710 | 20.266 | 10368.750 | 200.948 | 9591.417 | 65.525 |
| blosc2-1thread | 40.30 | 1.349 | 62060.546 | 834989.478 | 32.975 | 496.490 | 71.781 | 407.573 | 534.609 |
| python-list | 512.00 | 0.082 | 31.719 | 44.976 | 81.557 | 353.169 | 4.958 | 165.826 | 40.832 |

## 1-bit comparison

| Library | Payload KiB | Get ns | Copy µs | Count µs | Gather 256 µs | Equals µs |
|---|---:|---:|---:|---:|---:|---:|
| python-bytes | 64.00 | 36.795 | 4.184 | 233.081 | 6.809 | 1.959 |
| array-B | 64.00 | 40.931 | 1.037 | 649.313 | 7.235 | 21.414 |
| numpy-u8 | 64.00 | 65.065 | 1.298 | 4.982 | 0.339 | 4.237 |
| tightarray-packed | 8.00 | 40.230 | 0.185 | 0.252 | 0.210 | 0.275 |
| tightarray-aligned | 8.00 | 39.530 | 0.181 | 0.244 | 0.295 | 0.278 |
| tightarray-api | 8.00 | 8414.633 | 16.038 | 43.607 | 13.063 | 37.385 |
| bitstring | 8.00 | 1806.905 | 2.552 | 102903.209 | 461.005 | 0.526 |
| bitformat | 8.00 | 762.563 | 5.384 | 10085.875 | 195.138 | 13.382 |
| blosc2-1thread | 10.80 | 74330.736 | 31.650 | 506.646 | 84.011 | 571.635 |
| ml_dtypes-u1 | 64.00 | 66.367 | 1.343 | 6.699 | 0.410 | 7.239 |
| bitarray | 8.00 | 37.860 | 0.175 | 0.233 | 2.317 | 0.255 |
| python-list | 512.00 | 31.642 | 81.603 | 565.042 | 4.970 | 47.117 |

## Codec

| Bits | N | Library | Method | µs/op |
|---:|---:|---|---|---:|
| 1 | 4096 | bitstruct-python | pack-from-list | 1168.469 |
| 1 | 4096 | bitstruct-python | unpack-to-list | 894.844 |
| 1 | 4096 | cbitstruct | pack-from-list | 58.097 |
| 1 | 4096 | cbitstruct | unpack-to-list | 45.488 |
| 1 | 4096 | tightarray-packed | pack-from-list | 24.958 |
| 1 | 4096 | tightarray-packed | unpack-to-list | 10.797 |
| 1 | 4096 | numpy-packbits | pack-from-list | 67.103 |
| 1 | 4096 | numpy-packbits | unpack-to-list | 23.901 |
| 1 | 4096 | bitstruct-c | pack-from-list | 44.058 |
| 1 | 4096 | bitstruct-c | unpack-to-list | 42.096 |
| 1 | 4096 | bpack-numpy | unpack-to-ndarray | 1.185 |
| 1 | 4096 | tightarray-packed | unpack-to-ndarray | 1.747 |
| 3 | 4096 | bitstruct-python | pack-from-list | 1505.125 |
| 3 | 4096 | bitstruct-python | unpack-to-list | 1006.906 |
| 3 | 4096 | cbitstruct | pack-from-list | 59.557 |
| 3 | 4096 | cbitstruct | unpack-to-list | 45.533 |
| 3 | 4096 | tightarray-packed | pack-from-list | 26.111 |
| 3 | 4096 | tightarray-packed | unpack-to-list | 12.964 |
| 3 | 4096 | numpy-packbits | pack-from-list | 103.173 |
| 3 | 4096 | numpy-packbits | unpack-to-list | 29.487 |
| 3 | 4096 | bitstruct-c | pack-from-list | 46.614 |
| 3 | 4096 | bitstruct-c | unpack-to-list | 43.284 |
| 3 | 4096 | bpack-numpy | unpack-to-ndarray | 12.659 |
| 3 | 4096 | tightarray-packed | unpack-to-ndarray | 1.951 |
| 5 | 4096 | bitstruct-python | pack-from-list | 1742.812 |
| 5 | 4096 | bitstruct-python | unpack-to-list | 1018.313 |
| 5 | 4096 | cbitstruct | pack-from-list | 59.521 |
| 5 | 4096 | cbitstruct | unpack-to-list | 45.862 |
| 5 | 4096 | tightarray-packed | pack-from-list | 26.952 |
| 5 | 4096 | tightarray-packed | unpack-to-list | 13.050 |
| 5 | 4096 | numpy-packbits | pack-from-list | 115.880 |
| 5 | 4096 | numpy-packbits | unpack-to-list | 34.245 |
| 5 | 4096 | bitstruct-c | pack-from-list | 46.344 |
| 5 | 4096 | bitstruct-c | unpack-to-list | 42.362 |
| 5 | 4096 | bpack-numpy | unpack-to-ndarray | 12.755 |
| 5 | 4096 | tightarray-packed | unpack-to-ndarray | 1.979 |
| 8 | 4096 | bitstruct-python | pack-from-list | 2149.813 |
| 8 | 4096 | bitstruct-python | unpack-to-list | 1018.636 |
| 8 | 4096 | cbitstruct | pack-from-list | 58.210 |
| 8 | 4096 | cbitstruct | unpack-to-list | 44.943 |
| 8 | 4096 | tightarray-packed | pack-from-list | 25.100 |
| 8 | 4096 | tightarray-packed | unpack-to-list | 10.859 |
| 8 | 4096 | numpy-packbits | pack-from-list | 95.525 |
| 8 | 4096 | numpy-packbits | unpack-to-list | 40.372 |
| 8 | 4096 | bitstruct-c | pack-from-list | 44.316 |
| 8 | 4096 | bitstruct-c | unpack-to-list | 43.007 |
| 8 | 4096 | bpack-numpy | unpack-to-ndarray | 0.767 |
| 8 | 4096 | tightarray-packed | unpack-to-ndarray | 1.403 |

## Matrix

| Bits | N | Library | Method | µs/op |
|---:|---:|---|---|---:|
| 5 | 65536 | python-list | get-scalar | 0.035 |
| 5 | 65536 | python-list | to-list | 138.944 |
| 5 | 65536 | python-list | construct-from-rows | 138.220 |
| 5 | 65536 | numpy-u8 | get-scalar | 0.082 |
| 5 | 65536 | numpy-u8 | to-list | 274.430 |
| 5 | 65536 | numpy-u8 | construct-from-rows | 1125.240 |
| 5 | 65536 | tightarray-packed | get-scalar | 0.053 |
| 5 | 65536 | tightarray-packed | to-list | 246.909 |
| 5 | 65536 | tightarray-packed | construct-from-rows | 783.011 |
| 5 | 65536 | tightarray-api | get-scalar | 13.014 |
| 5 | 65536 | tightarray-api | to-list | 288.677 |
| 5 | 65536 | tightarray-api | construct-from-rows | 8769.417 |
| 5 | 65536 | blosc2-1thread | get-scalar | 35.104 |
| 5 | 65536 | blosc2-1thread | to-list | 309.159 |
| 5 | 65536 | blosc2-1thread | construct-from-rows | 1182.042 |

## Ragged

| Bits | N | Library | Method | µs/op |
|---:|---:|---|---|---:|
| 5 | 66683 | python-list | get-row-to-list | 0.137 |
| 5 | 66683 | python-list | get-scalar | 0.037 |
| 5 | 66683 | python-list | to-list | 199.958 |
| 5 | 66683 | python-list | construct-from-rows | 215.539 |
| 5 | 66683 | tightarray-packed | get-row-to-list | 0.242 |
| 5 | 66683 | tightarray-packed | get-scalar | 0.053 |
| 5 | 66683 | tightarray-packed | to-list | 335.659 |
| 5 | 66683 | tightarray-packed | construct-from-rows | 928.927 |
| 5 | 66683 | npstructures | get-row-to-list | 1.568 |
| 5 | 66683 | npstructures | get-scalar | 9.517 |
| 5 | 66683 | npstructures | to-list | 717.313 |
| 5 | 66683 | npstructures | construct-from-rows | 1561.771 |

## Set

| Bits | N | Library | Method | µs/op |
|---:|---:|---|---|---:|
| None | 65536 | python-set | membership | 0.050 |
| None | 65536 | python-set | intersection | 244.641 |
| None | 65536 | python-set | union | 347.607 |
| None | 65536 | python-set | construct | 273.005 |
| None | 65536 | intbitset | membership | 0.044 |
| None | 65536 | intbitset | intersection | 0.329 |
| None | 65536 | intbitset | union | 0.347 |
| None | 65536 | intbitset | construct | 428.239 |

## Coverage

Executed Python libraries: bitarray, bitstring, bitformat, ml_dtypes, Blosc2, bitstruct (Python/C), cbitstruct, bpack, npstructures, intbitset. Baselines: list, bytes, array.array, NumPy, and both native tightarray layouts plus the Array API adapter.

The benchmark covers construction, scalar get/set, independent copy/slice, count, gather, sum, equality, and conversion. It does not measure every API method, mutation under concurrency, or out-of-core workloads. Unsupported operations are absent rather than assigned an infinite time. There is no comparison with a biosequence application layer.

## Interpretation and reproducibility

- Inputs: seeded uniform small unsigned integers; additional 95%-zero cases for bits 1, 5, 8. Sizes 4,096 and 65,536. Full width/distribution results and timing samples are in the companion JSON/CSV.
- Construction starts from an already materialized Python list for every library; creation of that input is excluded. Blosc2 includes conversion to ndarray.
- Copy and slice-copy produce independent data; NumPy/native view creation is not compared against copying.
- Scalar get includes Python call/conversion overhead. Set/restore measures two assignments and a confirming read. Packed Array API assignment currently copies/scatters the array, so this path is expected to be costly.
- Gather returns 256 values. NumPy/native gather receives prebuilt intp indices; bitarray receives a prebuilt Python index list. Libraries without a gather primitive use Python scalar loops, identified by the adapter source.
- Native Array sum currently uses Python iteration; bitarray sum uses count(1), and its gather uses native list indexing. Array API operations may unpack/compute/repack. Whole equality returns one bool for every backend.
- Codec pack starts from a Python list; unpack-to-list and unpack-to-ndarray are separate. NumPy packbits includes converting integers into individual bits, since it is not an arbitrary-width integer pack API.
- Set operations intentionally have their own section: order and duplicates are discarded. They are not array substitutes.
- Thread environment: OMP_NUM_THREADS=OPENBLAS_NUM_THREADS=VECLIB_MAXIMUM_THREADS=NUMEXPR_NUM_THREADS=1; Blosc2 compression/decompression nthreads=1.
- Payload is encoded data size or pointer storage, not total process RAM. traced_result_bytes and traced_peak_bytes cover only allocations visible to tracemalloc; C/Rust private allocators can be absent. Do not rank total memory by shallow_object_bytes.
- PyFastPFor 1.4.0 could not build on ARM64: its bundled x86 intrinsic headers reject this architecture. No timing is invented for it.
- Julia BitArray is measured separately in competitors-julia.csv after JIT warmup. Its native Julia call overhead is different, so it is excluded from Python rankings.
- pysdsl had no PyPI distribution. Building official source and submodules failed in SDSL louds_tree.hpp (nonexistent m_select1/m_select0 members); no performance conclusion is drawn.

Reproduce with `python benchmarks/competitors.py --output competitors.json`, using `benchmarks/competitors-requirements.txt`. Render with `python benchmarks/report_competitors.py competitors.json docs/competitor-performance.md`.

For Julia: `python benchmarks/prepare_julia.py /tmp/competitor-inputs`, then `JULIA_NUM_THREADS=1 julia --startup-file=no benchmarks/competitors_julia.jl /tmp/competitor-inputs/julia-input.bin /tmp/competitor-inputs/julia-indices.txt competitors-julia.csv`.

## Julia reference (separate runtime)

Same 65,536 binary values and 256 gather indices. Julia 1.13.0, one thread, after JIT warmup. These timings exclude Python interoperability and are not part of the Python ranking. Retained bytes use Julia summarysize.

| Library | Method | µs/op | Retained bytes |
|---|---|---:|---:|
| Julia-BitArray | copy | 1.253 | 8256 |
| Julia-BitArray | count | 0.130 | 8256 |
| Julia-BitArray | sum | 0.130 | 8256 |
| Julia-BitArray | gather-256 | 0.719 | 8256 |
| Julia-UInt8 | copy | 1.878 | 65576 |
| Julia-UInt8 | count | 10.320 | 65576 |
| Julia-UInt8 | sum | 4.218 | 65576 |
| Julia-UInt8 | gather-256 | 0.161 | 65576 |
