# All cold payloads use native packing

The isolated candidate, pinned to `2ba7a15`, replaces Array construction plus `_raw` at trimmed spans, periodic patterns, and both palette-candidate branches with `_direct_payload`. Existing translation buffers and all record metadata, candidate ordering, codec filters and decisions are retained. Hot/decode mutable Array construction is untouched. The measured transformation was subsequently adopted in production.

Nine randomized paired repeats of 80 operations cover 4093-byte high-label palettes with2/8/32/128 symbols; periods31/127/256 with partial final repetitions; width3/5/8 trimmed spans of509 elements; and width3/5/8 direct controls. Encode, single-chunk construction, and alternating actual changed16-byte writes followed by flush are measured. Trim writes occur inside the physical span; other writes start at3. Each final logical result and sealed chunk matches the baseline. Codec settings remain level5/typesize1/nthreads1 and packed NOFILTER/dense BITSHUFFLE. This is a synthetic microbenchmark, not application E2E.

Grouped median candidate/baseline time ratios (less than1 is faster):

| Codec | Group | Encode | Construct | Changed write+flush |
|---|---|---:|---:|---:|
| none | palette | 0.963 | 0.966 | 0.955 |
| none | period | 0.947 | 0.964 | 0.971 |
| none | trim | 0.964 | 0.975 | 0.963 |
| none | direct | 1.000 | 1.002 | 1.005 |
| lz4 | palette | 1.008 | 0.988 | 1.020 |
| lz4 | period | 0.981 | 0.998 | 1.021 |
| lz4 | trim | 0.988 | 1.039 | 0.993 |
| lz4 | direct | 1.013 | 0.989 | 0.986 |
| zstd | palette | 0.980 | 1.005 | 0.990 |
| zstd | period | 0.952 | 0.999 | 0.993 |
| zstd | trim | 1.047 | 1.020 | 1.021 |
| zstd | direct | 1.017 | 1.015 | 1.020 |

The no-codec cases support a modest3–5% reduction in overhead, while direct controls remain effectively unchanged. Codec results are noisy and do not establish a broad improvement. The strongest regression is palette8/LZ4 changed-write+flush (+6.6%); unchanged direct3/ZSTD construction also regresses5.8%, and direct8/LZ4 encode5.3%. ZSTD trim encode regresses about4.7% in the grouped median. These measurements justify no codec-speed claim.

Exact-output tests cover all three codecs, palette on/off, the workload families, and short high-label inputs of lengths1–80. They compare both sealed bytes and every compressor input/filter in order. Optional Blosc tests skip when unavailable. The injector is idempotent; after production adoption, an AST reversal restores old Array packing only at the changed cold sites, so correctness tests do not need Git history.

All117 timing rows passed equality and source/binary guards. After measurement, idempotent injection and the live-source reconstruction oracle were added. The artifact benchmark hash therefore identifies the measured script version, not the later edited script; the pinned historical transformation and timed workload are unchanged. Raw samples and guards are retained in `compressed-all-payloads-results.json`.

```sh
python -m pytest -q tests/test_compressed_all_payloads.py
python -m benchmarks.compressed_all_payloads --repeats 9 --operations 80 --output docs/compressed-all-payloads-results.json
```

Integrated verification: CPython 3.12 full suite 1367 passed; CPython 3.14 1044 passed, 89 optional-dependency skips. Official typing checks, strict mypy on compressed.py, Ruff and diff whitespace checks passed. The live-source exact-output oracle is included in storage-pilots CI. No native code changed.
