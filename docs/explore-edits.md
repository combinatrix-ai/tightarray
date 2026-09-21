# Online categorical-field mutation pilot

Synthetic 16-million-element categorical fields, not a real editing app.
Each operation reads a scalar, increments it modulo state count, writes it,
and reads the new value before the next operation. 256 indices are visited
per round for three rounds; checksums and full resulting arrays match NumPy.
The same sequence is used for every backend. Uniform random 8/32-state fields
and piecewise-constant runs of 256 are tested. Repeated indices become hot.

Blosc2 NDArray uses 64KiB chunks, 8KiB blocks, BITSHUFFLE, LZ4/ZSTD level5,
one compression/decompression thread. This is the direct scalar API, with
no deferred chunk-batched editing. Different chunk sizes, block-edit APIs or
an uncompressed dirty-chunk cache can change this tradeoff and are not tested.
NumPy+Numba supplies an optimized batch-loop ablation with identical resulting
edits; its compilation is excluded. Packed uses the ordinary CPython scalar API.

Reproduction:

```sh
python -m benchmarks.explore_edits
python -m pytest -q tests/test_explore_edits.py
```

For uniform 8-state data, median per 256 edits:

| Backend | Stored bytes | Time |
|---|---:|---:|
| NumPy scalar API | 16 MiB | 0.0605 ms |
| NumPy + compiled loop | 16 MiB | 0.0007 ms |
| tightarray scalar API | 6 MiB | 0.0406 ms |
| Blosc LZ4 | 6.135 MiB | 32.6773 ms |
| Blosc ZSTD | 6.072 MiB | 58.0215 ms |

Packing permits direct writes while compressed NDArray scalar writes must
update the affected compressed region. The very large difference here is
specific to this deliberately fine-grained access contract. It is not a
claim against tuned/batched compressed editing or an application E2E ratio.
Nor is packing fastest versus the compiled dense loop.

For runs of 256 identical values, Blosc ZSTD stores the 8-state field in about
0.220 MiB versus packed's 6 MiB. It is therefore the capacity winner on that
structured input, despite slower immediate scalar updates. 32-state behavior
shows the same tradeoff; all raw samples and build timings are recorded in
[results](results/explore-edits.json). Storage is payload including compressed
chunk headers/packed word padding, not RSS, Python object size or allocator
capacity. Initial dense source and validation outputs are retained by this
comparative experiment. The update cost excludes ingestion and final full
validation. Three short timing samples are exploratory, not robust latency
percentiles. The immutable full-data size is 16 MiB before encoding.
