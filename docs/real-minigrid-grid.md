# Actual MiniGrid encoded-grid snapshot pilot

This experiment executes actual MiniGrid environment steps and the library's
`Grid.encode` / `Grid.decode` pipeline. It stores the **encoded world grid**, not
observation replay. It deliberately does not replace the live object grid.

Source inspected in installed MiniGrid: `minigrid/core/grid.py` and
`minigrid/core/world_object.py`. In particular, `Door.toggle` mutates the object
returned by `Grid.get`; a packed categorical value cannot transparently preserve
that identity/mutation contract. `Box.contains` is absent from `WorldObj.encode`,
and upstream `WorldObj.decode` recreates a Box with no contents. Object positions,
agent position/direction, carried objects, RNG, mission and other environment
state are also not a complete part of this encoding. **Neither this adapter nor
upstream Grid.encode/decode is a general environment checkpoint.**

The adapter uses existing tightarray APIs: three Arrays at widths 4, 3, 2 for
object type, color and object state. It preserves the encoded uint8 tensor and
visibility-mask behavior exactly. The snapshot is immutable relative to later
world mutations; reconstructing a Grid creates new objects.

## Reproduction and method

```sh
python -m benchmarks.real_minigrid_grid --output docs/results/real-minigrid-grid.json
python -m pytest tests/test_real_minigrid_grid.py
```

MiniGrid and gymnasium are optional pilot dependencies. The benchmark takes 20
actual seeded steps in Empty-16x16, DoorKey-16x16 and MultiRoom-N6, retaining full
world-grid encodings. These random traces are not successful task-solving
policies. Separate targeted tests exercise unlocking a Door with a matching Key,
Box contents loss, and invisible cells.

For each frame the reference is actual upstream encode/decode. The timed pipeline
starts from real Grid objects and executes `Grid.encode`, storage construction,
dense encoded-grid retrieval, and `Grid.decode`. A second timer isolates only
storage construction plus retrieval from an already-encoded array. Five repeats
follow correctness warmup. Environment stepping is not in these timers, and the
experiment makes no claim of faster training or environment steps.

Comparison backends are NumPy uint8, tightarray, and Blosc2 BITSHUFFLE with LZ4 or
ZSTD at compression level 5 and one thread. Each compressed grid is an independent
frame; default compressor blocking is used. `payload_bytes` counts packed native
buffers or compressed frame bytes. `storage_object_shallow_bytes` includes the
owned storage objects (`sys.getsizeof`), including native allocation for tightarray
and NumPy and bytes storage for Blosc; the packed tuple is included. Neither is
RSS or whole-object-graph size. Snapshot wrapper, shape tuple and object-world
storage are excluded.

## Results

Measured MiniGrid 3.1.0, NumPy 2.5.3 and Blosc2 4.13.1 on macOS arm64.
All 60 actual trace frames round-tripped exactly for every backend; 7 focused
tests passed. Median complete pipeline times below process all 20 grids.

| Environment | Backend | Payload/grid | Owned storage bytes/grid | Pipeline/20 grids |
|---|---|---:|---:|---:|
| Empty 16² | NumPy | 768 | 912 | 5.708 ms |
| Empty 16² | packed | 288 | 568 | 5.888 ms |
| Empty 16² | Blosc ZSTD | **109** | **142** | 6.015 ms |
| DoorKey 16² | NumPy | 768 | 912 | 5.766 ms |
| DoorKey 16² | packed | 288 | 568 | 6.034 ms |
| DoorKey 16² | Blosc ZSTD | **135** | **168** | 6.610 ms |
| MultiRoom 25² | NumPy | 1875 | 2019 | 14.281 ms |
| MultiRoom 25² | packed | 720 | 1000 | 14.191 ms |
| MultiRoom 25² | Blosc ZSTD | **330** | **363** | 14.989 ms |

There is **no compelling packed-backend application win here**. MiniGrid world
encodings are small and highly spatially structured; compression stores less than
packing, and live object-world storage remains allocated regardless. The small
MultiRoom timing variation is not evidence of a speedup: object reconstruction
dominates, and the storage-only packed roundtrip is slower than NumPy.

For DoorKey's 20 frames, storage-only roundtrip medians are NumPy 0.019 ms,
packed 0.173 ms, LZ4 0.211 ms and ZSTD 0.303 ms. Packing trades extra space against
a small absolute saving versus compression, while still losing to dense copies.
The 62.5% payload reduction versus uint8 shrinks to about 37.7% when the owned
storage objects are counted, before counting the snapshot wrapper or live world.

This supports **deprioritizing live MiniGrid world replacement**. It would require
object identity and mutation integration for little storage value on these grid
sizes. Snapshot archives and replay are distinct workloads; this experiment does
not establish their end-to-end value.
