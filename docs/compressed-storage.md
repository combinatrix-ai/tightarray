# Adaptive compressed storage experiment

`tightarray.compressed.CompressedArray` is an experimental, fixed-length **uint8**
container. It combines per-chunk representation choices with a byte-bounded cache
of packed arrays, compact cyclic patterns, and trimmed spans. It is useful when local alphabets are much smaller than
the global value range, or when a packed working set fits the cache but a uint8
working set does not. Existing `Array`, Matrix, and Array API behavior is unchanged.

This implementation manages chunks in Python and uses the existing C packing
kernels. It is not a universal replacement for NumPy, nor a new entropy codec.
The initial measurements favored read-mostly workloads. Subsequent native input
and metadata optimizations also improve construction and updates; tiny working
sets and some codec-heavy operations remain slower. See the
[optimization measurements](compressed-storage-optimization.md).

## Use

```python
from tightarray.compressed import CompressedArray

a = CompressedArray.full(1_000_000, 0, chunk_size=4096, cache_bytes=64 * 1024)
a[100] = 250
a.write(4090, [250, 251] * 16)  # May span chunks; validates the entire input first.
assert a[100] == 250
data: bytes = a.read(4080, 4130)
copy: bytes = a[::2]           # Slices are independent bytes, not array views.
a.flush()                     # Re-encode dirty chunks, retaining the hot cache.
print(a.storage_info())
a.clear_cache()               # Flush, then release the packed cache.

# Optional extra compression:
# python -m pip install 'tightarray[compression]'
b = CompressedArray([250, 251] * 8192, codec="zstd")  # Or codec="lz4".
```

Defaults: `chunk_size=4096`, `cache_bytes=262144`, `codec="none"`, `palette=True`.
The `none` codec still performs uniform/local-palette/bit-packing/run/periodic/trimmed compression,
with no NumPy, Numba, or Blosc2 import. LZ4/ZSTD use optional Blosc2, compression
level 5 and one thread. The optional Blosc2 4.x extra requires Python 3.11+;
the no-codec path retains the package's Python 3.10+ requirement. See the upstream
[compress2](https://blosc.org/python-blosc2/reference/autofiles/low_level/blosc2.compress2.html)
and [decompress2](https://blosc.org/python-blosc2/reference/autofiles/low_level/blosc2.decompress2.html)
interfaces used by the implementation.

Values must implement `__index__` and fit 0..255. Negative scalar indices work;
`read(start, stop)` and `write(start, values)` use explicit nonnegative bounds.
There is no resizing, slice assignment, ndarray dispatch, Numba descriptor, or
public persistence format. Physical widths are internal and adapt without a
widening warning; this class never accepts values outside logical uint8. It is
not governed by the separate Array API namespace's storage-widening policy.
Public stubs contain no `Any` and are checked from the built wheel.

## Representation and writeback

Cold chunks choose the smallest retained payload plus palette among these
candidates (not every conceivable encoding):

1. A single scalar for a uniform chunk, stored directly in the chunk index.
2. Direct packed values or uint8 bytes (bytes can beat word padding on tiny tails).
3. Packed local palette indices plus their actual uint8 values.
4. With a codec: compressed direct/palette-packed bytes using NOFILTER, and
   compressed uint8 using BITSHUFFLE. Candidates smaller than 64 bytes skip the
   codec. Incompressible candidates stay uncompressed; equal-size ties favor the
   earlier uncompressed candidate.
5. Runs encoded as ULEB128(run length minus one) plus a value/index byte. A
   decode palette is retained when it narrows hot storage; `palette=False` uses
   direct values. Only a strictly smaller payload plus palette wins. Run scanning
   stops once it cannot beat the best uncompressed form. With LZ4/ZSTD, all potentially winning
   codec candidates are still evaluated, and uncompressed runs compete with the
   winner (runs are not additionally fed to the codec).
6. A packed pattern of at most 256 values, plus one byte storing its length minus
   one. At least two repetitions are required; a partial final repetition is
   allowed. The shortest exact period is detected in C with bounded scratch.
   Direct and palette-indexed patterns compete by their actual word-rounded
   payload plus palette size; direct wins ties. Only a strictly smaller total
   than the existing candidate wins. Period records compete
   with runs and codec candidates without additional entropy compression.
7. A default value plus a packed interior span, omitting matching leading/trailing
   values. Up to two endpoint defaults compete; chunks larger than 65535 values
   skip this uint16-bounded format. An eight-byte private header records default,
   width, palette length, start and span length. Safe size bounds reject losing
   candidates before scanning their interior; codec none packs only the winner.
   Codec-backed encoding preserves every potentially winning full-chunk codec candidate.

Nonuniform cold chunks retain one bytes object: a private descriptor followed by
palette and payload. Most descriptors occupy two bytes; trimmed descriptors occupy
eight. The common two bytes are included in `owned_bytes` but excluded from
`stored_bytes`. The trimmed format's additional six descriptor bytes remain
in `stored_bytes`; it always equals cold record length minus the common two bytes
for nonuniform chunks. Uncompressed candidate sizes are calculated before allocating
the winning representation. Codec trials are skipped only when their palette plus
the public Blosc minimum header length already exceeds the best known payload
size. Equal bounds still run, preserving codec tie priority. This exact pruning
preserves the winning record; see [measurements](compressed-header-pruning.md).

A cache hit reads a packed `Array`, translating local palette indices where needed.
Periodic entries retain only their packed pattern and use cyclic indexing; bulk
reads expand directly into the requested output. Trimmed entries retain only their interior and answer exterior reads with the
default value. Scalar and partial bulk writes wholly inside a cached span update
its packed interior in place when the current width and palette suffice. Bulk
writes validate all input first; a native span setter then checks bounds, palette
membership and storage width for every value before its first store. Unsupported
writes return to the materializing path without mutation. The setter uses fixed
stack scratch for palette lookup, without a persistent table or encoded bytes
allocation; failed fallback allocation leaves that chunk unchanged. These updates
retain the existing hot width and palette until the entry is replaced or reloaded.
Other changed structural
writes materialize an ordinary packed entry, so changing one element cannot
change other repetitions or defaults. Uncached entries still use write-through;
editing a temporary decoded span alone would not persist the change.
Ordinary cached entries also apply partial bulk writes directly when their
current width and palette represent every input value. Like scalar updates, this
retains the hot width and palette even when the last large value or a label is
removed; the cache can therefore remain larger than immediate repacking would
require. Flush recomputes cold storage from logical values, while clearing and
reloading releases the old hot representation. Full-chunk replacements still
repack. Width/palette growth chooses a new compact hot representation before
replacing the old one. The LRU budget includes each cached
packed buffer (only the pattern or interior for structural entries) and its palette. With `cache_bytes=0`, or a chunk larger than that budget, writes
are immediately encoded and reads use only a temporary decoded chunk.

Cold payload remains allocated while a chunk is cached, even while stale after a
write. A dirty cache entry is authoritative. Eviction/flush builds its replacement
before swapping the cold entry or dropping the cache. Encoding failures preserve
the pending data. A multi-chunk `write` validates the entire iterable and bounds
before modification; codec/allocation failures can leave an already completed
prefix committed. It is not a transactional store or a thread-safe container.

## What memory measurements mean

`storage_info()` separates:

- `logical_bytes`: length of the equivalent uint8 buffer.
- `stored_bytes`: all retained cold payload and palettes, including stale copies
  of cached chunks. Call `flush()` to inspect the latest cold encoding.
- `cache_bytes`: packed hot payload and palettes; always within `cache_limit_bytes`.
- `owned_bytes`: a `sys.getsizeof` estimate of the retained object graph including
  Python chunk/cache metadata and both cold and hot storage, deduplicated by object
  identity. Shared runtime/codec objects and allocator overhead are excluded.
- `rle_chunks` counts run records; `periodic_chunks` counts short-pattern records;
  `trimmed_chunks` counts default-plus-interior records; `compressed_chunks` counts
  Blosc2-compressed records. Palette counts can overlap
  these formats. Cache hit/miss/eviction counters
  are separate. Direct uniform
  reads bypass cache admission and do not count as hits or misses.

These are **not process RSS**. A cache miss allocates scratch before eviction.
Encoding considers multiple candidates; `read` retains result pieces before joining
them, and `write` materializes its entire input for validation. Peak memory also
includes several chunk-sized buffers, requested output/input, and codec scratch.
`full()` creates uniform chunks without a full dense input. Zero uniform payload
does not mean zero memory: the scalar index still occupies space.

## Reproducible experiment

```sh
python -m pip install -e '.[test,compression]'
python -m pytest -q tests/test_compressed.py
python -m benchmarks.compressed_storage
```

The [benchmark](../benchmarks/compressed_storage.py) compares NumPy uint8, regular
`Array`, the three CompressedArray codec options, and **Blosc2 with a matching
byte-bounded decoded-uint8 LRU and dirty writeback**. This is a custom baseline,
not a claim about every Blosc2 NDArray operation. Both use 64 KiB cache budgets,
4096-element chunks, one codec thread, and level 5; the baseline uses BITSHUFFLE.

Each of six synthetic datasets has 1,048,576 values: random 8 or 32 states,
two arbitrary labels in 128..255 per source region, uniform regions, 32-element
runs, or 0.1% nonzero spikes. Source regions remain 4096 elements when storage
chunks are swept over 1024/4096/16384. Selected zero-cache controls are included.
There are 84 case/backend rows, each with three repeats in rotated backend order.
Seeds and implementation/benchmark SHA256s are in the
[raw results](compressed-storage-results.json).

Timed scalar phases contain 256 reads over 8, 32, or all chunks. Local/medium
phases prewarm the same trace for each backend; global reads start with an empty
cache. Range reads copy 64 bytes at 64 locations. Updates change 64 scalar values
then include `flush()` in the timing. All values are checked before and after
updates, including full cold reloads; verification is outside timing. This is a
storage microbenchmark, not application E2E or a fixed-RSS capacity result.

### Results on ARM64 macOS, 2026-09-21

CPython 3.12.8, NumPy 2.5.3, Blosc2 4.13.1. Retained memory below includes Python
metadata with an empty cache; timings are medians for 256 reads spread over
32 chunks. The dense comparison is ZSTD plus the same 64 KiB cache budget.
Memory uses decimal KB (1000 bytes).

| Data | CompressedArray codec | Its cold KB | Dense ZSTD cold KB | Its read ms | Dense ZSTD read ms |
| --- | --- | ---: | ---: | ---: | ---: |
| Random 8 states | none | 432.3 | 420.2 | 0.106 | 0.729 |
| Random 32 states | none | 694.4 | 682.3 | 0.295 | 0.694 |
| Two high labels per region | none | 179.0 | 257.4 | 0.110 | 0.780 |
| Uniform regions | none | 7.2 | 29.2 | 0.068 | 0.706 |
| 32-element runs | zstd | 107.7 | 80.0 | 0.688 | 0.898 |
| 0.1% nonzero spikes | zstd | 57.1 | 37.7 | 0.828 | 0.705 |

The local-two case uses 203.0 KB including the warmed cache versus 326.6 KB for
dense ZSTD, while reading about 7.1 times faster. Random8 uses almost equal warm
memory, 489.2 versus 489.4 KB, but packed caching gets 256 hits and zero misses;
the dense cache gets 124 hits and 132 misses. Uniform regions need no hot cache.

There are clear losing cases. Local-two construction takes 32.4 ms versus 4.8 ms
for dense ZSTD, and 64 edits plus flush take 3.01 versus 1.59 ms. Enabling ZSTD
on CompressedArray does not shrink this input further but raises build time to
141.9 ms and edits/flush to 25.6 ms from candidate evaluation. When both working
sets fit in their caches, its 8-chunk read batch takes 0.110 ms versus 0.070 ms.
Regular `Array` and NumPy remain faster: their medium read batches are about
0.011 and 0.018 ms, respectively, using about 1.049 MB for these high labels.

Rare spikes show why payload alone is insufficient: CompressedArray+ZSTD retains
18.8 KB of payload versus the baseline's 26.5 KB, but **57.1 versus 37.7 KB after
metadata**. For runs32, ZSTD payloads are equal (68.7 KB); extra chunk metadata
makes CompressedArray larger, and global reads take 2.08 versus 1.68 ms. This
experiment does not establish an advantage over dedicated sparse representations.

Chunk size changes both locality and representation. With 1024-element chunks,
the 32-chunk dense working set fits its cache and is faster. With 16384-element
chunks, four different local-two regions share one storage palette and cold
packing can lose to ZSTD compression. No single chunk size or codec wins throughout.

Validation: 40 focused compressed-array tests, including injected codec failures,
randomized updates and optional-dependency isolation; 660 repository tests; strict
implementation mypy plus wheel-packaged stubs and no-Any consumer fixtures. The
storage CI job also runs the codec tests with its pinned Blosc2 dependency.

## Design choices from the experiment

The initial implementation promoted palette growth to direct-value packing.
Keeping a palette in the hot cache instead preserves its capacity advantage when
a third or fifth local label appears. Tests cover these transitions and write-through
when the resulting representation exceeds the budget.

We also tried scanning every decoded uint8 chunk for a new palette. On the runs32
dataset, the ZSTD global-read batch rose from about 2.1 ms to 8.6 ms in the exploratory
runs. This optimization was rejected: a cold uint8 candidate now decodes using its
known width. Likewise, compressed direct-packed chunks retain their encoded width.
This can leave hot-cache compression opportunities unused, but avoids a scan on
each cache miss. A future cold descriptor could preserve suitable hot metadata.

The first uniform representation used a Python record for each chunk. Including
metadata made its cold footprint larger than the Blosc2 baseline despite a zero
payload. Uniform chunks now use the scalar itself as the index entry. Measurements
must include this metadata cost, especially with small chunks.

The current choice is to keep this separate experimental class, with no extra codec
by default. Next useful work is to move metadata/codec selection onto a cheaper
path and test a real application access trace under a measured process-RSS budget.
Adding general ndarray semantics before resolving these costs is deferred.
