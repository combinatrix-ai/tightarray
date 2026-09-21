# Reuse the alphabet while planning trimmed spans

Removing a prefix/suffix consisting of the selected default value leaves every
other global value inside the retained span. The exact span alphabet is therefore
the complete input alphabet, with the default removed only if it does not occur
inside. The native planner now uses `memchr` to test that occurrence and reuses
the already computed sorted alphabet. It avoids rebuilding a 256-entry presence
table by scanning every interior byte. Candidate sizes, palettes and tie order
are unchanged. The private API continues to require complete alphabet metadata;
it checks shape/order, not completeness, and malformed metadata remains bounded.

The [raw measurements](compressed-trim-alphabet-results.json) contain five pairs
of fresh old/new worker processes, randomized within each pair. Each worker uses
11 samples of 100 calls for 192 configurations: 24 inputs × two palette settings
× planner/encode-with-none/LZ4/ZSTD. Inputs cover 512/4096/16384 elements, 3/5/8-bit
spans with the default absent or present inside, differing endpoints, and random
controls. A common Python callable wrapper is included in both timings. Encoder
measurement does not include construction or updates.

The packages have identical Python files at `debeb6e`; their old/new native
binaries differ. Their [source manifests](compressed-trim-alphabet-manifests.json)
and the actually imported binary/Python hashes are retained. Every planner tuple
and complete encoded record has the same SHA-256 across both workers in every
pair. Workers check their source hashes before/after timing. Native oracle tests
also compare complete tuples against an independently expressed Python policy.

Median new/old ratios below first take the median of five paired ratios for each
configuration, then summarize configurations in the named group:

| Operation | Span cases | Differing endpoints | Random controls |
|---|---:|---:|---:|
| Planner | 0.685 | 0.655 | 0.200 |
| Complete encode, none | 0.943 | 0.927 | 0.997 |
| Complete encode, LZ4 | 0.988 | 0.985 | 1.000 |
| Complete encode, ZSTD | 0.991 | 0.990 | 1.011 |

The isolated planner is called with a permissive `len(raw)+2` limit. Real encoder
pruning often avoids planning random data, explaining why that large planner-only
gain does not translate to complete encoding. Span codec-free encode ratios range
0.892–0.978; span LZ4 0.952–1.018; span ZSTD 0.976–1.038. Some codec cases are slower:
the optimization is not a general codec or application throughput win. Five process
pairs on one machine do not establish performance on other hardware.

```sh
python benchmarks/compressed_trim_alphabet.py --old /path/to/old-package-root --new /path/to/new-package-root --pairs 5 --repeats 11 --calls 100 --output results.json
python -m pytest tests/test_compressed_trim_alphabet_native.py tests/test_compressed_trim_alphabet.py
```

The native test suite covers default presence/absence, both endpoint candidates,
palette-width boundaries, randomized complete alphabets, and malformed private
metadata safety. The benchmark smoke test checks all measured phases and source
records. Production native tests are included in the storage-pilots CI job.

Integrated verification: CPython 3.12 full suite 1344 passed; CPython 3.14
1037 passed and 81 optional-dependency skips; isolated ASan/UBSan 69 passed;
Ruff and diff whitespace checks passed. This change does not alter Python types.
