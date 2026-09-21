# Direct 8-bit bulk memcpy isolation

The [benchmark](../benchmarks/compressed_memcpy.py) uses separate fresh worker
processes for the old and new extensions. Both packages contain byte-identical
Python files pinned to `6ea92e7`; only the binary differs. This avoids the invalid
comparison of two pinned Python encoders that would both call the same new C
kernel. Baseline package was preserved before rebuilding, and the candidate
copies those Python files with the new `6d1cddf` extension. Later typed-input
Python dispatch changes do not enter either worker.

[Raw results](compressed-memcpy-results.json) are unchanged. Package manifests
and source guards passed before/after, including all native headers, core source,
benchmark helpers and binary hashes. Baseline binary SHA256 is
`eefd8b64495a5d4541f24a8ce25f733fd2480e0340c956d11aabebdcb54b3f6c`;
candidate is `d75c1c7090bcdaf380e8b2bfd087c22aadf07c83b3f2621c23d4f3ca335d5f36`.
Twenty-four smoke tests pass, and independent fresh-process checks confirm each
snapshot actually imports its intended extension.

Five paired repetitions randomize old/new process order. Each worker measures
100 native configurations and 100 public configurations. Startup/imports are
excluded. Native batches use 257 alternating actual-changing writes on packed and
word-aligned arrays with view offsets 0/7, widths 1/16/64/256/4096, direct 8 target
and direct/palette 3/5 controls. Public batches use 17 changed writes plus flush,
budgets 0/65536 and none/ZSTD. Odd counts ensure even full-array cycles finish
with different values from the initial data. Native guards verify the whole view
and untouched neighbors; public guards verify full logical values and cache
bounds after flush/reload. Posthoc comparison confirms identical public cold
SHA256 and stored/cache bytes in every before/after/reloaded sample.

## Native kernel

Speedup old/new across packed/word-aligned and offsets 0/7. Calls contain no codec
or public input processing. This is not an application throughput measure.

| Bytes/write | Minimum speedup | Median | Maximum |
|---:|---:|---:|---:|
| 1 | 0.951× | 0.977× | 0.988× |
| 16 | 1.600× | 1.711× | 1.798× |
| 64 | 5.160× | 5.242× | 5.314× |
| 256 | 17.396× | 17.637× | 17.712× |
| 4096 | 115.676× | 121.812× | 130.794× |

The large direct 8-bit kernel win follows removal of per-byte packed extraction
and assignment. One-byte operations are slightly slower in this run (median
speedup 0.977×). Direct/palette 3/5 controls have median candidate/baseline time
ratio 1.009, range 0.870–1.062; their kernels are unchanged. Word-aligned and shifted
views preserve exact values and adjacent bytes.

## Public direct 8-bit write + flush

Milliseconds for 17 writes, same pinned Python in both workers:

| Budget | Bytes/write | Codec | Old binary | New binary | Speedup |
|---:|---:|---|---:|---:|---:|
| 0 | 1 | none | 0.193625 | 0.206833 | 0.936× |
| 0 | 1 | zstd | 0.852709 | 0.905375 | 0.942× |
| 0 | 16 | none | 0.203125 | 0.196625 | 1.033× |
| 0 | 16 | zstd | 0.874334 | 0.866625 | 1.009× |
| 0 | 64 | none | 0.192666 | 0.192500 | 1.001× |
| 0 | 64 | zstd | 0.870500 | 0.854708 | 1.018× |
| 0 | 256 | none | 0.198792 | 0.198542 | 1.001× |
| 0 | 256 | zstd | 0.878500 | 0.903333 | 0.973× |
| 0 | 4096 | none | 0.176625 | 0.172000 | 1.027× |
| 0 | 4096 | zstd | 0.874084 | 0.862875 | 1.013× |
| 65536 | 1 | none | 0.024792 | 0.025875 | 0.958× |
| 65536 | 1 | zstd | 0.067125 | 0.068208 | 0.984× |
| 65536 | 16 | none | 0.025208 | 0.028583 | 0.882× |
| 65536 | 16 | zstd | 0.079958 | 0.068708 | 1.164× |
| 65536 | 64 | none | 0.027041 | 0.025375 | 1.066× |
| 65536 | 64 | zstd | 0.077750 | 0.077750 | 1.000× |
| 65536 | 256 | none | 0.039333 | 0.026042 | 1.510× |
| 65536 | 256 | zstd | 0.090250 | 0.069667 | 1.295× |
| 65536 | 4096 | none | 0.067750 | 0.063167 | 1.073× |
| 65536 | 4096 | zstd | 0.103958 | 0.107667 | 0.966× |

The public benefit is much smaller: cached 256-byte writes improve 1.51× without
compression and 1.30× with ZSTD. Cached 64-byte writes improve 1.07× none and are
approximately equal with ZSTD. Cached 16-byte none regresses 0.025208→0.028583 ms
(13.4%), whereas ZSTD improves 1.16×. Public full-chunk replacement bypasses the
partial hot path, so the native full-width result does not predict a matching
public gain. There is no 121× public-write claim.

Uncached direct 8-bit time ratios have median 0.995, range 0.968–1.068. Public 3/5
and palette controls have median 0.999, range 0.851–1.381; these short phases show
visible process/run variability and include sampled regressions. All raw repeats
remain available. No default inference of broad speedup follows from those
control fluctuations. Cold/hot payload is unchanged; retained graph excludes
shared runtime, codec scratch and allocator arenas and is not RSS. Dense codecs
are intentionally absent from this native-kernel isolation experiment.

Reproduction requires two package roots containing the same pinned Python files
and the independently built old/new extension. The worker enforces Python file
hash equality and checks package hashes across the run:

```sh
python -m benchmarks.compressed_memcpy --baseline /path/to/old-package-root --candidate /path/to/new-package-root --repeats 5 --output /tmp/memcpy.json
python -m pytest -q tests/test_compressed_memcpy_benchmark.py
```

A [separate robust follow-up](compressed-memcpy-confirm.md) did not reproduce
the initial 16-byte none regression at that magnitude and confirms repeatable
64/256-byte cached benefits. The original artifact above remains unchanged.
