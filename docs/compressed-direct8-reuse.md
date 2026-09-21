# Direct8 candidate payload reuse

This isolated prototype loads baseline `99377a7` and a modified copy of the same Python source against the same native binary. Production was unchanged during measurement; the measured transformation was subsequently adopted with a typed helper. The candidate replaces `Array(raw, bits=8)` plus `_raw` with the original immutable bytes when length is divisible by eight, or a single zero-padded bytes result otherwise. Packed/raw candidate order, bit width, palette selection, compression filters, pruning and ties are preserved. Narrow packed candidates still use Array packing.

Eight tests compare exact sealed outputs and every compression payload/filter call for both palette settings, all three codecs, lengths 1–80, random widths, and periodic/run/trim cases. Separate checks establish identity reuse and exact word padding. All passed, as did Ruff. After production adopted the typed helper, the tests load current source and reconstruct an Array-packing oracle by reversing helper calls; this keeps correctness coverage independent of Git history. Injection is idempotent. Optional codec tests skip when Blosc2 is unavailable.

Integrated validation: CPython 3.12 full suite 1238 passed; CPython 3.14
936 passed, 76 skipped (optional dependencies absent); official typing checks
and strict mypy on `tightarray/compressed.py` passed. The exact-output tests
are included in the storage-pilots CI job. No native source or binary changed.

The corrected run uses 11 randomized paired repeats of 100 operations per case. Encode and one-chunk construction are measured separately. Update measurements alternate a precomputed changed 16-byte piece (each original byte XOR 1) and the original piece, flushing after every update; every iteration changes values. Final logical values and cold bytes are verified against the baseline encoder. This is a synthetic microbenchmark, not an application E2E result. Compression remains clevel5, typesize1, nthreads1, NOFILTER for packed and BITSHUFFLE for dense bytes.

Median microseconds per operation:

| Input | Codec | Encode baseline → reuse | Construct baseline → reuse | Changed write + flush baseline → reuse |
|---|---|---:|---:|---:|
| direct8, 4096 | none | 7.24 → 6.75 | 8.19 → 7.68 | 8.19 → 7.69 |
| direct8, 4096 | LZ4 | 23.11 → 22.59 | 24.63 → 22.94 | 23.68 → 22.97 |
| direct8, 4096 | ZSTD | 45.30 → 44.57 | 47.29 → 47.21 | 47.31 → 46.82 |
| direct8, 4093 | none | 6.38 → 6.36 | 7.40 → 7.40 | 7.39 → 7.52 |
| direct8, 4093 | LZ4 | 22.13 → 21.45 | 24.09 → 23.34 | 23.96 → 22.90 |
| direct8, 4093 | ZSTD | 44.60 → 44.98 | 46.44 → 46.67 | 46.41 → 46.72 |

Aligned direct8 gives a modest, consistent improvement; codec CPU limits its effect. Tail/no-codec already chooses dense bytes, so that case is effectively unchanged. ZSTD tails show no useful win. Strongest control regressions were direct3/4096 ZSTD changed-write+flush (37.51→39.07µs, +4.2%), direct3/4093 none encode (5.77→5.99µs, +3.7%), and direct5/4096 ZSTD changed-write+flush (42.73→44.22µs, +3.5%). The prototype introduces a helper call for narrow candidates, so these controls should not be declared improved; an inline width8 branch would avoid that specific overhead and needs its own measurement before acceptance.

The initial artifact is retained as `results/compressed-direct8-reuse-same-value.json`. Its write-flush phase repeatedly wrote the existing value and is **not** a changed-update trace. Encode/constructor evidence remains meaningful, but the table above exclusively uses the corrected `results/compressed-direct8-reuse.json`. Both artifacts retain their original source/binary guards and raw paired samples; the corrected run passed all guards. The initial benchmark source hash differs because the update trace was corrected afterward.

Reproduce the corrected experiment from this repository:

```sh
python -m pytest -q tests/test_compressed_direct8_reuse.py
python -m benchmarks.compressed_direct8_reuse --repeats 11 --operations 100 --output docs/results/compressed-direct8-reuse.json
```

After the corrected timed run, the benchmark injector gained idempotence and an AST-based reverse transform for testing the adopted live helper; tests gained optional-codec skips. Therefore the artifact’s benchmark hash identifies the measured script version and does **not** match the subsequently edited script. Those changes do not alter the pinned99377a7 timing transformation or workload. The recorded guards verified source stability during each run; they are not a claim that the present script matches the historical hash.
