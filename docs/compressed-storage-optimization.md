# Compressed storage optimization measurements

The target remains broader performance improvements against Blosc2, not a claim
of general superiority. These are synthetic storage microbenchmarks against the
custom byte-bounded Blosc2 LRU in `benchmarks/compressed_storage.py`, not application
E2E or all Blosc2 APIs. NumPy and ordinary packed Array remain separate baselines.

## Changes and evidence

Baseline: commit `134cb8b`, recorded in `compressed-storage-results.json`.
Native helpers: `8568fd7`; input/native integration and cold metadata: `e18d432`.
The final measurement additionally selects the uncompressed winner by its exact
size before allocating it. No approximate compression-selection heuristic is used.

1. Consume contiguous unsigned-byte buffers a chunk at a time rather than converting
   each NumPy scalar in Python. Signed, multibyte, and strided inputs retain logical
   element validation. No mutable input alias is retained.
2. Scan the uint8 alphabet and restore native dense packed words in C. The restore
   helper validates width, size, overflow and tail bits; it is distinct from the
   big-endian word-aligned wire helper.
3. Retain each nonuniform cold chunk in one bytes object with a two-byte descriptor,
   replacing the retained dataclass, length integer and separate palette/payload.
   Uniform chunks remain scalar integers. Payload accounting excludes descriptors;
   retained-object accounting includes them.
4. Without a codec, calculate exact word-rounded candidate lengths first, preserving
   the prior candidate order on ties. Allocate only the selected packed/raw/palette
   representation. Codec-backed paths still compare all existing candidates.

The full final run is [recorded here](compressed-storage-optimized-results.json).
[Intermediate stage summaries](compressed-storage-optimization-stages.json) retain
source hashes, all median timings, and first-repeat initial retained storage;
intermediate per-repeat traces are not included in that summary. Stage comparisons
are separate runs, not randomized paired trials: small differences can be noise.
The benchmark uses 84 rows, three repeats, rotated backend order, one codec thread,
and verifies full contents and cache bounds outside timing.

## Observed results

ARM64 macOS, CPython 3.12.8, NumPy 2.5.3, Blosc2 4.13.1; 1 MiB logical inputs,
4096-element chunks and 64 KiB hot-payload budget. Times are milliseconds.
The final none path builds all six inputs in 0.329–1.916 ms, compared with
2.531–4.218 ms for dense LZ4 and 3.452–41.607 ms for dense ZSTD in that run.
The original none path took roughly 30–34 ms. This includes input ingestion.

| Dataset / selected storage | Cold owned bytes before metadata change | After | Dense ZSTD |
| --- | ---: | ---: | ---: |
| random8 / none | 432,305 | 405,033 | 420,243 |
| local-two / none | 178,960 | 143,273 | 257,448 |
| rare-spikes / ZSTD | 57,061 | 30,221 | 37,746 |
| runs32 / ZSTD | 107,657 | 80,414 | 80,001 |

These sizes are retained `sys.getsizeof` graphs, not RSS or scratch memory.
The metadata comparison is from the native and metadata stage runs. It shows why
payload-only comparisons hid a material Python-object cost. Runs32 still loses
slightly in retained size to dense ZSTD.

For the final local-two none path, medium reads take 0.112 ms vs dense ZSTD
0.720 ms, global reads 0.362 vs 1.217 ms, and updates plus flush 0.965 vs
1.923 ms. Local hot reads still lose: 0.113 vs 0.073 ms. This is not a universal
win: none retains far more cold data than a codec on long runs or rare spikes.
Codec-backed tightarray still pays for several compression trials and can lose
substantially in construction/update time. Descriptor slicing also adds a copy on
cold decode; no general cold-read speed improvement is claimed for that change.

## Codec-policy experiments (not adopted)

`benchmarks/compressed_codec_policy.py` preserves experiments in
[main results](compressed-codec-policy-results.json) and
[follow-up results](compressed-codec-policy-followup.json). Those measurements
used the earlier Python alphabet scan; their timing is not the current native path.

Skipping compression based on alphabet entropy missed periodic structure and
increased size by up to about 30 times. Compressing only the smallest uncompressed
representation also lost substantially on adverse patterns. Both are rejected.
A smallest-first probe reduced calls and observed time with under 0.6% worst
whole-dataset size increase in the follow-up set, but this is not a bound for
unseen data. It has not replaced the exhaustive default.

## Remaining experiments

- Reduce Python dispatch and bookkeeping on scalar cache hits.
- Avoid payload slicing copies when restoring sealed packed chunks.
- Reduce codec setup/candidate costs without silently degrading storage quality.
- Measure broader distributions, actual applications and peak/RSS capacity;
  synthetic retained-object wins alone do not establish general superiority.

## Scalar cache dispatch

The next change inlines scalar index validation and cache-hit handling in
`__getitem__`. It avoids `_index`/`_get_hot` Python calls on hits and accesses cold
metadata only on misses. Bounds/index-protocol behavior, LRU order and dirty cache
authority are preserved. Full benchmark results are in
[the hot-read run](compressed-storage-hot-results.json), with source hashes.
For the six primary cases, nonuniform local reads measure 0.085–0.096 ms instead
of the prior 0.112–0.117 ms range. Dense ZSTD measures 0.068–0.074 ms in the new
run, so the hot path still does not win. Uniform local reads are 0.063 ms.
This is an independent run; the uniform global timing is noisy (0.152 ms median)
and no broad uniform-path speedup is claimed.

## Restoring packed data without a temporary payload copy

The private native restore helper now accepts a byte offset into an immutable
source. Uncompressed packed cold chunks copy directly from the sealed record to
owned words, avoiding a temporary payload bytes slice. Compressed and raw-byte
representations retain their existing decode paths. Offset bounds, remaining
length, integer overflow and tail normalization are validated in C.

[The offset run](compressed-storage-offset-results.json) records the same full
84-row suite. Main nonuniform none global reads fall from 0.324–0.587 ms in the
hot-dispatch run to 0.303–0.516 ms, depending on dataset. Random8 with a zero-byte
cache measures 0.273 vs 0.367 ms; at 16 KiB chunks it measures 0.460 vs 0.618 ms.
Not every configuration improves (local-two 16 KiB is essentially unchanged).
Uniform chunks do not use this path; their differences are run-to-run noise.

## Reusing Blosc2 codec contexts (not adopted)

The [portable context experiment](../benchmarks/compressed_codec_context.py)
compares 2,045 actual candidates across 14 distributions in seven paired,
randomized repetitions. A reusable SChunk per codec/filter/payload-length preserves
compressed bytes and decoded contents in this set. Candidate compression time
falls from 16.77 to 12.06 ms for LZ4 (1.39x) and from 108.56 to 99.70 ms for ZSTD
(1.09x). Context creation costs approximately 0.39/0.55 ms separately. See
[raw timing results](compressed-codec-context-results.json).

Reusing just one slot per filter across varying lengths changes output in
1,061/2,045 candidates, sometimes changing compressed size. That shortcut is
rejected. These are observed equivalence results for length-keyed pools, not an
upstream guarantee for every future codec version.

[Fresh-process RSS measurements](compressed-codec-context-memory.json) show why
unconditional per-array pooling is not adopted: 100 nine-context pools increase
RSS by approximately 51.33 MB for LZ4 and 128.37 MB for ZSTD (0.51/1.28 MB per pool).
A 256 MiB safety guard stops larger runs. Native context memory dwarfs retained
compressed scratch payload. Clearing pools and collecting does not lower RSS;
allocator retention means this is not evidence of a live-object leak. A bounded
shared scratch pool could amortize cost, but needs separate concurrency, lifetime,
parameter-isolation and whole-operation/RSS evaluation before adoption.

## Native hot entries

The cache entry now holds its Array/palette references and dirty flag in C. Scalar
reads decode and translate the palette in one native call. Bulk reads avoid
allocating an Array slice wrapper and translate directly into the freshly allocated
result bytes. The Python LRU, admission budget, codec selection and dirty-write
failure ordering remain unchanged. Retained-size accounting explicitly visits
entry data and palette; the native object size is shallow.

[Full benchmark results](compressed-storage-native-hot-results.json) and a
[nine-repeat paired comparison](compressed-native-hot-paired.json) are retained.
The paired test randomizes Python/native order per repeat for all six `none`
datasets, restoring the Python entry implementation from commit `1fb408a` while
using the same native Array helpers. The portable reproducer is
`python -m benchmarks.compressed_hot_paired --output /tmp/paired.json` (requires
that baseline commit locally); the recorded run used its equivalent temporary
script before packaging, not a freshly rerun benchmark after script formatting.

Paired nonuniform local reads improve by roughly 2–8%, global reads by 7–16%, and
local-two block reads from 0.118 to 0.104 ms. These are modest gains; global/mixed
read paths benefit more than hot hits. Dense Blosc2 still wins some hot-hit and
codec-heavy operations. Uniform read paths bypass native entries, so their small
timing differences are noise. Native-entry behavior was checked under ASan/UBSan,
including array views, both layouts, all widths, ownership and invalid palettes.
