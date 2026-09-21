# Semantic-label volume pilot

This is a synthetic storage-and-patch-materialization experiment, **not MONAI,
medical segmentation, or another application's end-to-end training benchmark**.
The target workload keeps a large low-cardinality label volume resident and
materializes small cubic patches for downstream work.

Run from the repository with NumPy, Numba and Blosc2 installed:

```sh
python -m benchmarks.explore_labels --output docs/results/explore-labels.json
python -m pytest tests/test_explore_labels.py
```

## Method

- Volumes: 128³ and 256³ uint8 labels, 8 or 32 categories, deterministic seed.
- Distributions: independent uniform labels; piecewise-constant random 8³ regions.
  Neither distribution is claimed to represent real clinical data.
- Samples: 16 random, generally unaligned cubes of width 4, 16 or 32. Every sampled
  byte must equal NumPy, including every measured repeat.
- NumPy: resident uint8 volume, slice copies into a newly allocated dense batch.
- NumPy+Numba ablation: the same patch-loop structure with direct uint8 loads,
  to separate packing from amortizing Python call overhead. Dense Numba indexing
  uses its default unchecked loads; packed helpers check each logical index.
- tightarray: one contiguous packed Array (3 or 5 bits/value), checked specialized
  Numba reads directly into the newly allocated dense batch. Only selected voxels
  are decoded; full rows or the full volume are never expanded.
- Blosc2: NDArray, 32³ chunks, 8³ blocks, BITSHUFFLE filter, either LZ4 or ZSTD,
  compression level 5; compression and decompression each use one thread. The
  blocks match the structured fixture's region scale, which favors spatial
  compression. Other partitions and real distributions can change the outcome.
- Storage: packed `nbytes`, dense `nbytes`, or compressed chunk `schunk.cbytes`.
  These are payload figures, not process RSS; Python/container metadata and the
  retained dense source and output batches are excluded. Build timing includes
  construction from an existing uint8 source. This is not a peak-capacity test.
- Each backend warms once before five alternating-order measured repeats.
  Materialization and batch allocation are included. The JSON preserves the
  first sampling time, which can include JIT (subsequent cases reuse signatures).
  Repeated locations can be cache hot; the experiment does not model disk I/O.

The focused tests cover both distributions and widths, a non-word-aligned volume
side, full-volume and boundary patches, and out-of-bounds requests.

## Results

The JSON records 120 cases (8 volume fixtures × 3 patch widths × 5 backends),
with exact sampled-output equality in every repeat. This is one short run on
macOS arm64; timings do not establish a general application speedup.

For a 256³ volume (16 MiB dense), resident payload is:

| Labels | Distribution | tightarray | Blosc LZ4 | Blosc ZSTD |
|---|---|---:|---:|---:|
| 8 | Uniform | 6.000 MiB | 6.812 MiB | 6.906 MiB |
| 32 | Uniform | 10.000 MiB | 10.844 MiB | 10.906 MiB |
| 8 | 8³ constant regions | 6.000 MiB | **0.878 MiB** | 0.937 MiB |
| 32 | 8³ constant regions | 10.000 MiB | 1.075 MiB | **1.071 MiB** |

Unused bit planes also compress in BITSHUFFLE: random low-cardinality labels are
not incompressible to Blosc. Packing's storage advantage is modest against this
strong baseline. Spatial structure strongly favors compression.

For the uniform 8-category 256³ volume, median time to allocate and materialize
16 patches (microseconds):

| Patch width | NumPy slice copies | NumPy+Numba | tightarray+Numba | Blosc LZ4 | Blosc ZSTD |
|---|---:|---:|---:|---:|---:|
| 4 | 20.33 | **5.21** | 10.75 | 261.79 | 266.71 |
| 16 | 49.62 | **35.58** | 282.96 | 500.58 | 551.79 |
| 32 | **258.50** | 389.71 | 2438.00 | 1556.88 | 1882.87 |

**Candidate niche:** small sparse patches from weakly spatially compressible
low-cardinality volumes. Tightarray is about 24× faster than the compressed
NDArray path for 4³ patches while storing slightly less. It does not beat the
strongest dense sampling baseline; its apparent win against NumPy's Python
slice loop disappears with the dense-Numba ablation. The absolute tiny-patch
batch saving is only about 0.25 ms, so downstream work could dwarf it.

For 32³ patches the compressor amortizes block expansion and is faster than
per-voxel packed reads. For coherent labels Blosc stores roughly 6–11× less than
tightarray, making it the capacity winner. Real semantic masks are often spatially
structured, so the synthetic random-label result alone is not a recommendation
for a segmentation application.

A next application experiment should use public real masks, actual patch shapes
and sampling distribution, compare a tuned compressed baseline, and measure
whole data-loader or training throughput plus peak RSS. The current pilot only
identifies where that experiment might be worthwhile.
