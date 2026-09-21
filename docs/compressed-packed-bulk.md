# Codec-free packed bulk writes

Three isolated native builds compare the existing scalar store loop with bulk validation/packing at thresholds 16 and 64 values. No compression codec is used: every public array has `codec="none"`. All variants use identical Python files, verified by SHA256; workers verify imported package, compressed module and extension paths are inside their assigned `lib` directory, preventing editable-checkout fallback.

The unchanged [raw results](compressed-packed-bulk-results.json.gz) are stored as deterministic gzip (`mtime=0`). They include hashes of all source headers/C files, loaded Python files and extension binaries for every worker. Nine fresh processes run three rotated rounds, each with five trials per configuration. The measured script hash is preserved in the artifact. All 575 configurations match data, neighboring elements, cold records and cache sizes exactly across variants; reload and source guards passed.

## Threshold decision

Use threshold 16. For packed 1–7-bit native writes of 16 values it reduces median per-call time by 12%, versus approximately unchanged at threshold 64. All 28 native configurations at that width improve with threshold16 (ratios 0.748–0.974). At 64 or more values the two thresholds have nearly the same performance. Public 16-value writes remain approximately flat because Python overhead dominates; this does not establish a public speedup at that width.

Each ratio below is the median across configurations of candidate time / baseline time. A configuration time is the median of its three worker medians. Native results include packed direct and palette widths1–7, both view positions; public results use cache65536. Smaller is faster.

| Write values | Native threshold16 | Native threshold64 | Public updates threshold16 | Public updates threshold64 | Public updates+flush threshold16 |
|---:|---:|---:|---:|---:|---:|
| 1 | 1.012 | 1.008 | 1.004 | 0.996 | 1.005 |
| 8 | 1.003 | 1.000 | 1.001 | 1.002 | 1.010 |
| 16 | 0.880 | 1.006 | 1.006 | 1.013 | 1.010 |
| 64 | 0.445 | 0.452 | 0.865 | 0.865 | 0.882 |
| 256 | 0.300 | 0.301 | 0.634 | 0.637 | 0.657 |
| 1024 | 0.245 | 0.247 | 0.401 | 0.402 | 0.413 |
| 4096 | — | — | 0.993 | 0.993 | 0.989 |

Public cached updates at 64/256/1024 values improve by approximately 1.16×/1.58×/2.49× at threshold16. Including flush, these become 1.13×/1.52×/2.42×. Full-chunk4096 writes use the existing replacement path and remain approximately unchanged. Native gains are not presented as public gains.

## Direct/palette groups and regressions

Table entries are group median / worst configuration ratio for threshold16. Short means1/8/16 values; long means64/256/1024, excluding full-chunk replacement. All use fitting cache65536 and widths1–7.

| Representation | Writes | Updates median/worst | Flush median/worst | Total median/worst |
|---|---|---:|---:|---:|
| direct | short | 0.997 / 1.032 | 0.997 / 1.212 | 1.003 / 1.053 |
| direct | long | 0.624 / 0.910 | 0.997 / 1.435 | 0.639 / 0.925 |
| palette | short | 1.007 / 1.051 | 1.008 / 1.279 | 1.010 / 1.062 |
| palette | long | 0.671 / 0.923 | 1.000 / 1.310 | 0.691 / 0.945 |

Short public updates have worst observed regressions of 3.2% direct and 5.1% palette; their total worst ratios are 1.053 and 1.062. Threshold64 does not remove short-case scatter (worst total1.059/1.074). Flush is not changed by the kernel, and its small absolute duration is noisy: worst threshold16 flush ratio1.435, while group medians stay0.997–1.008. The improvement is in updating cached packed data, not cold encoding. No significance test or universal no-regression guarantee is claimed.

Control medians for threshold16: direct8 native/public pooled1.008 (range0.945–1.087); public budget0/512 total1.001 (0.972–1.057); word-aligned widths3/5/6/7 native1.007 (0.950–1.060). The latter layout cannot use the dense packed kernel. Widths1/2/4 divide a word exactly and are included in the raw layout matrix.

Example: direct5-bit, aligned1024-value public writes (129 actual changes of the region) take369.92→148.38 microseconds for updates and377.96→155.58 microseconds including flush. Palette5-bit takes398.54→188.88 microseconds for updates and408.12→199.04 including flush. These timings exclude construction and validation.

## Workload and provenance

Native matrix:15 representations (direct1–8 and high-label palette1–7) ×2 storage layouts ×2 view positions ×6 widths =360 configurations. Root views use offsets0/7, with write starts0/3. Each trial warms with a write and restore, then times257 alternating writes. Full logical root equality checks both neighbors and unwritten interior values.

Public matrix:180 fitting-cache partial configurations,15 full-chunk controls and20 budget0/512 fallback controls. Each trial constructs a fresh4096-element array, prewarms one scalar read, then times129 alternating changed writes and flush separately. Every written value changes on every call; the odd call counts leave a changed final array. Five fresh-object trials per worker avoid hidden cross-trial state. Construction, imports/startup and checks are outside timers. Native numbers are per call; public timings are whole129-write batches.

Builds came from `/tmp/ta-packed-bulk-experiment/{baseline,candidate16,candidate64}/lib`. The parent build script passed `CFLAGS=-DTIGHTARRAY_BULK_WRITE_THRESHOLD=16` or64 to isolated `setup.py build_ext --force --build-temp objects --build-lib lib`; baseline lacks the new bulk path. All three builds passed the parent native114-test selection before timing. Source headers for candidate16/64 are identical; compiler macro and binary hashes distinguish them. No untracked local build path is required by the benchmark: use `--root` to supply equivalent prepared package trees.

```sh
python -m benchmarks.compressed_packed_bulk --root /path/to/prepared-builds --rounds 3 --trials 5 --output packed-bulk.json
```

Reproduce with CPython3.12 and the recorded binaries/source builds. Production tests, sanitizer and portable builds are handled separately by the parent. This study changes only its benchmark and report artifacts.

## Adopted implementation and validation

The baseline source is `fabe8ec0955ca697f4979378c6da4fc5f5925cff`; commit `c92a9ad` adopts the threshold16 kernel. It validates the entire input before mutation, handles the head/tail with scalar stores, and packs byte-aligned bodies with existing NEON kernels. Palette translation uses a bounded 512-byte scratch buffer. Direct 8-bit writes retain their existing memcpy path; word-aligned layouts with per-word gaps retain scalar stores. The shared kernel also serves span-cache writes. No codec-selection or compression behavior was changed; timing claims here cover `codec="none"` only.

After rebuilding production extensions, the full suites passed: CPython 3.12 **1461 passed**; CPython 3.14 **1116 passed, 95 skipped** (optional dependencies unavailable). Official wheel typing checks and focused Ruff checks passed. Isolated ASan/UBSan and `TIGHTARRAY_NO_NEON` builds each passed **149 tests**, with imported extension paths and sanitizer symbols verified. The new public regression tests cover cached identity, changed partial writes, chunk crossing, cache-budget fallbacks, flush and reload; native tests cover all widths/layouts, nested views, exact physical edge preservation and late-invalid atomicity. Both new test files are included in the storage CI job.
