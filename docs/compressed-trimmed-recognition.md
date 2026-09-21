# Native modal recognition comparison

The benchmark-only trimmed-span prototype now accepts an optional recognizer.
The default retains the historical NumPy histogram implementation. This study
substitutes `_byte_trim`, an exact native modal recognizer with lowest-value tie
breaking, while preserving original exhaustive encoding, candidate selection,
palette scans, packing, Python hot access and expansion before mutation.

[Raw results](compressed-trimmed-recognition-results.json) are copied unchanged
from the measured run. The [portable script](../benchmarks/compressed_trimmed_recognition.py)
uses the same seven datasets, 1 MiB size, 4096-byte chunks, 64 KiB cache and
operation traces as the [initial study](compressed-trimmed-policy.md). Five
paired repetitions randomize eight methods (baseline, Python recognition and
native recognition for none/ZSTD, plus dense LZ4/ZSTD). Python baseline source
is pinned to `eff5443`; the current native extension is hashed separately.
Guards include both benchmark scripts, the harness, native binary, existing
native sources, and explicitly `_compressed_trim.h`. The historical artifact
has not been rewritten or assigned a new script hash.

Every operation returned the expected contents. Every Python/native cold chunk
was also byte-identical for both codecs. Nine prototype tests passed. The native
helper's separate correctness and sanitizer suite is maintained with that helper.
All retained graph sizes match between recognizers; graph accounting includes
prototype instance and slot state but excludes shared runtime state, allocator
arenas and temporary/native codec workspaces. It is not RSS.

Construction medians in milliseconds (baseline / Python / native):

| Case | None | ZSTD |
|---|---:|---:|
| Random half, zero half | 1.872 / 7.170 / 4.576 | 12.789 / 18.743 / 16.017 |
| Zero half, random half | 2.046 / 7.306 / 5.151 | 13.439 / 19.970 / 16.710 |
| Central random island | 1.636 / 7.933 / 4.922 | 11.754 / 19.715 / 15.057 |
| Random 32 labels | 1.819 / 4.565 / 2.942 | 12.496 / 15.923 / 12.781 |
| Half with edge outlier | 1.968 / 5.672 / 3.323 | 13.932 / 17.887 / 15.045 |
| Rare spikes | 1.305 / 7.023 / 4.280 | 14.641 / 22.411 / 18.003 |
| Uniform chunks | 0.323 / 0.368 / 0.386 | 0.325 / 0.418 / 0.340 |

For the three cases that select trimmed spans, native recognition removes
29.5–38.0% of prototype construction time without a codec and 14.5–23.6% with
ZSTD. It still loses to the baseline in every case. Uniform chunks bypass both
recognizers, so their sub-millisecond differences are measurement variability.
Random data, edge outliers, and rare spikes preserve the baseline encoded size
but retain extra recognition/selection work.

For random-half/zero-half data, 64 updates plus flush take 0.540 / 1.949 / 1.399
ms without a codec and 3.130 / 4.509 / 3.948 ms with ZSTD. The central island
still costs 0.931 / 1.916 / 1.364 ms and 2.842 / 4.478 / 4.220 ms respectively.
Recognition improves some mutation costs but cannot remove structural expansion
or duplicate encoding work. Local/global scalar and block reads are included in
the artifact; both recognizers produce the same representation and access code,
so differences between their short read timings are not evidence of a faster
read algorithm. No default adoption follows from this study.

```sh
python -m benchmarks.compressed_trimmed_recognition --output /tmp/recognition.json
pytest -q tests/test_compressed_trimmed_policy.py
```
