# Modal-value candidate sizes: next-representation reconnaissance

This is **size arithmetic for hypothetical formats**, not an implemented codec,
RSS/owned-memory measurement, or performance result. It uses the same fourteen
1 MiB datasets and 4096-element chunks as the RLE study: primary seed 812 and
adverse-pattern seed 681. Each chunk's default is its most frequent value;
ties choose the lowest value. No codec-skipping heuristic is proposed.

Three lossless component layouts were evaluated:

1. **Trimmed span:** retain only the interval between the first and last
   non-default values. Header: 8 bytes for tag, default, width, palette count,
   uint16 start and span length. Interior default values remain in the span.
2. **Exception bitmap:** a one-bit-per-cell presence mask plus packed non-default
   values. Header: 8 bytes including two uint16 metadata fields.
3. **RLE presence:** alternating presence-run lengths, encoded as unsigned
   LEB128, plus packed non-default values. Header: 11 bytes, including the
   initial presence bit and encoded run-length byte count.

All value streams choose the smaller of direct packing and a local palette,
including palette bytes. Packed buffers round up to 8-byte words, matching the
current physical storage convention. Uniform chunks retain the existing
zero-payload scalar representation. Logical chunk length is external metadata.
The script verifies exact reconstruction from each representation's components;
it does not implement the proposed on-wire headers or native access paths.

| Dataset | Current none + RLE | Current ZSTD + RLE | Dense ZSTD | Best new candidate |
|---|---:|---:|---:|---:|
| Half random / half zero | 655,872 B | 343,550 B | 346,881 B | Trim: **329,728 B** |
| Skewed 8 states | 393,728 B | 240,274 B | 250,385 B | Bitmap: **212,608 B** |
| Periodic sparse high values | 133,664 B | **60,045 B** | 112,109 B | RLE presence: 88,410 B |
| Rare spikes | **7,590 B** | **7,590 B** | 26,470 B | RLE presence: 8,235 B |

The first two candidates reduce encoded bytes by approximately 4.0% and 11.5%
relative to the existing ZSTD results without applying a codec to the new
format. They save approximately 49.7% and 46.0% versus codec-none. Other
patterns mostly favor existing formats; any future implementation should
compare actual candidate sizes and retain the smaller encoding.

Trimmed spans need a bounds check followed by ordinary packed access. Exception
bitmaps need rank/popcount to locate a non-default value. Optional uint16 rank
checkpoints every 256 cells add 32 bytes/chunk: the skewed case becomes
220,800 bytes, still about 8.1% below its existing ZSTD result. This is a size
estimate, not evidence that indexed reads will be fast. RLE presence has no
ZSTD win in this matrix and is lower priority.

## Baseline accounting and provenance

Comparisons read the recorded `compressed-rle-integrated-results.json`;
**no current CompressedArray code is executed**. Existing packed/RLE baseline
`stored_bytes` excludes its two descriptor bytes, so the analysis adds two
bytes per nonuniform chunk. Dense Blosc headers are already counted. Python
metadata, allocator overhead and temporary decoding storage are excluded.

The checked-in result JSON is unchanged from the original `/tmp` analysis,
which ran before the portable refactor. The portable script adds explicit
baseline-artifact hashing to future outputs; it does not retroactively assign
its own source hash to that older run. If a follow-up runs CompressedArray
itself, pin baseline commit `aafc50b` rather than silently changing comparators.

```sh
python -m benchmarks.compressed_modal_candidates --output /tmp/modal-sizes.json
```

[All fourteen size comparisons](compressed-modal-candidates-results.json)
