# Native packed candidate bytes

The private `_pack_bytes` kernel creates word-padded bytes directly, avoiding
an intermediate Array, word exporter and copy. It retains the existing NEON
packing patterns and writes local integer results with `memcpy`, without
assuming that the Python bytes payload is uint64-aligned. Invalid values are
rejected before returning a result; unused tail bits and bytes are zeroed.

The [raw study](compressed-native-payload-results.json) loads pinned `faf98fd`
Python and changes only its narrow direct-payload helper to call the new native
method. Both policies use the same new extension; the baseline still uses the
unchanged Array implementation. Thus this measures choosing the new kernel,
not an old/new extension comparison. Existing Python direct8 identity reuse
and palette/period/trim packing are unchanged in this study.

There are 189 configurations: 21 inputs, three codecs, and encode/construction/
changed-write-plus-flush phases. Each uses 11 randomized paired samples of 100
operations. Writes alternate changed/original 16-byte pieces and flush every
time. Exact final logical values and cold records are checked, and all measured
source/binary hashes remain in the artifact. Tests also compare every codec
candidate payload and filter with the Array-based oracle.

For direct 1–7-bit inputs across 4093/4096 lengths, median candidate/baseline
ratios were:

| Phase | No codec | LZ4 | ZSTD |
|---|---:|---:|---:|
| Encode | 0.942 | 0.973 | 0.996 |
| Construct | 0.955 | 0.980 | 0.992 |
| Changed write + flush | 0.953 | 0.970 | 0.992 |

Representative 4096-element codec-free encode times: 3-bit 5.73→5.33 µs;
5-bit 6.31→5.97 µs. Changed-write-plus-flush: 3-bit 7.38→6.99 µs;
5-bit 8.01→7.63 µs. Codec timing is noisy and does not show a general ZSTD
win: the 5-bit ZSTD update case regressed 43.13→44.83 µs (+4.0%), while
3-bit improved 39.14→37.07 µs. These are one-process microbenchmarks, not
application E2E or independent-machine replications. Removing intermediate
allocation is established; universal throughput improvement is not.

The narrow direct helper was adopted. Integrated checks: CPython 3.12 full
suite 1317 passed; CPython 3.14 1011 passed and 80 optional-dependency skips;
official typing checks and strict mypy passed. An isolated non-NEON build
passed 256 tests; an isolated ASan/UBSan build passed 124 tests, including
all-position invalid-value checks. Production and native exact-output tests
are included in the storage-pilots CI job.

```sh
python -m benchmarks.compressed_native_payload --repeats 11 --operations 100 --output results.json
python -m pytest tests/test_compressed_native_payload.py
```
