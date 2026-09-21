# Public memcpy confirmation

The [initial study](compressed-memcpy.md) showed a noisy 13.4% regression for
cached direct 8-bit 16-byte writes without a codec, alongside much larger native
kernel gains. This bounded follow-up tests that public path more robustly.
The initial artifact and script remain unchanged. The
[new wrapper](../benchmarks/compressed_memcpy_confirm.py) records a separate
[confirmation artifact](compressed-memcpy-confirm-results.json).

Both immutable extension snapshots are unchanged, and both packages still use
byte-identical pinned `6ea92e7` Python. Only native binaries differ. Each of five
randomized old/new fresh-process pairs runs 31 independently constructed and
prewarmed trials per configuration. Every trial performs 17 real-changing partial
writes plus flush, with cache 65536, then checks all values, cold hash consistency,
flush/reload and cache bounds. Construction/imports and verification are excluded
from timing. Cases are direct 8 target and direct 5 control, widths 1/16/64/256,
none/ZSTD. All 31 raw timings are retained. Package/source guards passed; no kernel
edit or rebuild occurred between the initial and confirmation runs.

Summaries first take the median of 31 timings within each worker, then compare
the five worker medians. The paired ratio is new/old for each process pair; the
ratio range is the observed five-pair range, not a confidence interval.

| Case | Bytes/write | Codec | Old median ms | New median ms | Paired ratio median | Paired range | Faster pairs |
|---|---:|---|---:|---:|---:|---:|---:|
| direct-5bit | 1 | none | 0.022042 | 0.021959 | 0.9981 | 0.9833–1.0424 | 3/5 |
| direct-5bit | 1 | zstd | 0.058750 | 0.058167 | 0.9817 | 0.9754–1.0338 | 3/5 |
| direct-5bit | 16 | none | 0.022500 | 0.022333 | 0.9889 | 0.9833–1.0037 | 4/5 |
| direct-5bit | 16 | zstd | 0.060250 | 0.059041 | 0.9944 | 0.9786–1.0028 | 3/5 |
| direct-5bit | 64 | none | 0.024833 | 0.024833 | 0.9950 | 0.9782–1.0256 | 3/5 |
| direct-5bit | 64 | zstd | 0.061542 | 0.060250 | 0.9763 | 0.9666–0.9925 | 5/5 |
| direct-5bit | 256 | none | 0.031583 | 0.031750 | 1.0053 | 0.9741–1.0283 | 2/5 |
| direct-5bit | 256 | zstd | 0.068500 | 0.069166 | 1.0085 | 0.9853–1.0231 | 2/5 |
| direct-8bit | 1 | none | 0.022917 | 0.022042 | 0.9636 | 0.9348–1.0038 | 4/5 |
| direct-8bit | 1 | zstd | 0.061583 | 0.062833 | 1.0284 | 0.9717–1.0575 | 1/5 |
| direct-8bit | 16 | none | 0.022375 | 0.022500 | 1.0055 | 0.9907–1.0225 | 2/5 |
| direct-8bit | 16 | zstd | 0.061875 | 0.062000 | 1.0041 | 0.9866–1.0168 | 1/5 |
| direct-8bit | 64 | none | 0.024792 | 0.021750 | 0.8792 | 0.8614–0.8985 | 5/5 |
| direct-8bit | 64 | zstd | 0.064125 | 0.062708 | 0.9780 | 0.9490–1.0215 | 4/5 |
| direct-8bit | 256 | none | 0.034375 | 0.022042 | 0.6490 | 0.6042–0.6748 | 5/5 |
| direct-8bit | 256 | zstd | 0.076250 | 0.064209 | 0.8421 | 0.8022–0.8945 | 5/5 |

The 16-byte none regression does not reproduce: paired median is only +0.55%,
with observed range −0.93% to +2.25%; the two median times are 0.022375/0.022500 ms.
Sixteen-byte ZSTD is likewise approximately equal. This supports interpreting
the earlier 13.4% sample as short-phase variability, not a persistent regression
of that magnitude; it does not prove zero overhead.

The 64-byte none benefit appears in all five pairs (paired ratio 0.879), as do
256-byte none (0.649) and ZSTD (0.842). One-byte ZSTD retains a small possible
cost: median ratio 1.0284, range 0.9717–1.0575, with only one faster pair. Direct 5
control paired medians range 0.976–1.009, and individual ratios 0.967–1.042.
No broad speedup is attributed to those unchanged controls. Stable public gains
are concentrated in larger cached partial writes; they are much smaller than
native-only memcpy ratios. There is no 121× public API speed claim.

These finite paired measurements distinguish a noisy first observation from a
repeatable workload effect. They are not a statistical proof of nonregression,
an end-application benchmark, or a substitute for the recorded correctness tests.
The same package paths used in the first study can reproduce this follow-up:

```sh
python -m benchmarks.compressed_memcpy_confirm --baseline /path/to/old-package-root --candidate /path/to/new-package-root --output /tmp/memcpy-confirm.json
```
