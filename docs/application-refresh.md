# Current non-Minecraft application refresh

Measured checkout `87f9557b72d064109c4f43faf5d2d4b1e1ac4e7f`, using the current native extension. These are fresh same-run comparisons, not speed ratios against historical artifacts. Existing application harnesses and historical outputs were left unchanged. The [raw artifact](application-refresh-results.json.gz) records 210 guards covering the wrapper, reused harnesses, tightarray Python/C/headers/loaded extension, pinned Sokoban source, and MiniGrid/Gymnasium Python sources. Guards and logical checks passed.

Both applications still demonstrate memory/latency tradeoffs. Neither experiment establishes faster RL training or attributes a gain to the newly optimized bulk-write SIMD kernel: Sokoban encodes keys, while this replay harness stores images and retrieves sampled transitions.

## Actual Sokoban reverse search

The pinned upstream `gym-sokoban` room generator runs its actual reverse DFS. Only visited-key encoding and the common visited-state cap are patched. All four backends preserve the complete variable board state against the same fixed room; only shape/dtype constant within each search are omitted by the compact encoders. The sparse baseline stores every differing tile index/value, not boxes alone. Source commit `8e06e44e8bf3bb8bc73eeb1e7f0354508ce3fc89` and SHA256 are enforced by the reused harness.

Three fresh processes per method/cap, with seeded randomized initial method order and rotation. Seed37,10×10 room,four boxes. Process startup/imports are excluded; room generation and reverse search are included. Identity checks match visited count,key-call count,score,result-board SHA and box mapping across every method/repeat.

| Cap | Method | Median seconds | Visited states | Key payload bytes | Retained keyset bytes |
|---:|---|---:|---:|---:|---:|
| 5000 | marshal | 0.2025 | 5000 | 4,025,000 | 4,714,504 |
| 5000 | uint8 | 0.1990 | 5000 | 500,000 | 1,189,504 |
| 5000 | tightarray | 0.2182 | 5000 | 200,000 | 889,504 |
| 5000 | sparse | 0.3171 | 5000 | 75,000 | 764,504 |
| 50000 | marshal | 1.0228 | 25226 | 20,306,930 | 23,236,756 |
| 50000 | uint8 | 0.9951 | 25226 | 2,522,600 | 5,452,426 |
| 50000 | tightarray | 1.1029 | 25226 | 1,009,040 | 3,938,866 |
| 50000 | sparse | 1.6080 | 25226 | 378,390 | 3,308,216 |

Cap5000 reaches5000 states with36770 key calls and score1440. Cap50000 naturally finishes at25226 states,192353 key calls and score1853; it does **not** demonstrate retaining50000 states.

Against uint8 keys, tightarray reduces retained keyset memory25.2% at the smaller cap and27.8% at the larger run, with9.7% and10.8% more elapsed time. At the larger run the sparse encoder retains even less (3.31MB versus3.94MB) but takes1.608s versus1.103s. Marshal is the original representation, but uint8 and sparse are the stronger practical comparators.

Retained memory sums `sys.getsizeof(set)` and its byte-string keys; payload counts only key bytes. It excludes the DFS stack, boards, dictionaries, allocator retention and process RSS. These numbers demonstrate a visited-key capacity reduction, not a measured maximum-solvable problem size. The10×10 board produces40-byte packed keys versus100-byte uint8 keys; Python/set overhead reduces the whole-keyset saving.

## Actual MiniGrid observations and replay batches

The existing harness collects2048 real transitions in each of three environments, using seed123 random actions and a64-step episode cap. It preserves both pre/post images,action,reward,termination/truncation,direction,mission identities and episode information. All sampled images and metadata match NumPy exactly. Each reported batch median covers five repeats of24 batches, each64 sampled transitions (index seed456). Construction has one measured sample per backend and should not be treated as a robust build-time comparison. Backend order is inherited unchanged from the existing harness.

| Environment | Backend | Image payload bytes | Total payload bytes | Batch milliseconds |
|---|---|---:|---:|---:|
| Empty-8x8 | numpy | 602,112 | 645,148 | 0.0059 |
| Empty-8x8 | packed4 | 301,056 | 344,092 | 0.0569 |
| Empty-8x8 | blosc-lz4 | 81,890 | 124,926 | 0.5575 |
| Empty-8x8 | blosc-zstd | 35,916 | 78,952 | 0.6933 |
| Empty-8x8 | blosc-lz4-single | 304,364 | 347,400 | 0.1051 |
| Empty-8x8 | blosc-zstd-single | 264,671 | 307,707 | 0.1814 |
| DoorKey-8x8 | numpy | 602,112 | 645,173 | 0.0060 |
| DoorKey-8x8 | packed4 | 301,056 | 344,117 | 0.0572 |
| DoorKey-8x8 | blosc-lz4 | 95,573 | 138,634 | 0.5726 |
| DoorKey-8x8 | blosc-zstd | 45,023 | 88,084 | 0.7135 |
| DoorKey-8x8 | blosc-lz4-single | 305,583 | 348,644 | 0.1060 |
| DoorKey-8x8 | blosc-zstd-single | 265,796 | 308,857 | 0.1605 |
| FourRooms | numpy | 602,112 | 645,134 | 0.0059 |
| FourRooms | packed4 | 301,056 | 344,078 | 0.0561 |
| FourRooms | blosc-lz4 | 79,728 | 122,750 | 0.5485 |
| FourRooms | blosc-zstd | 36,600 | 79,622 | 0.6985 |
| FourRooms | blosc-lz4-single | 292,513 | 335,535 | 0.1005 |
| FourRooms | blosc-zstd-single | 253,176 | 296,198 | 0.1574 |

Packed4 halves image payload and reduces total payload about46.7% versus NumPy, but sampled batches are about9.5× slower. It is about10–12× faster than32-transition Blosc chunks, whose payloads are substantially smaller. The closest latency/capacity comparator is single-transition LZ4: packed4 samples about1.8× faster while total payload is similar, sometimes slightly larger. Single-transition ZSTD stores less and samples more slowly.

Blosc uses level5,BITSHUFFLE,typesize1,one thread. MiniGrid memory measures payload only, including common transition metadata, not retained object graph or process RSS. This is replay storage/retrieval, not a training loop, learning-quality evaluation or simulator-step replacement.

## Reproduction

```sh
python -m benchmarks.application_refresh --source /path/to/pinned/room_utils.py --repeats 3 --output application-refresh.json.gz
```

The source hash must match the pinned upstream file. The wrapper launches each Sokoban sample and the MiniGrid matrix in fresh subprocesses and verifies all source hashes before and after work. The resulting gzip is deterministic (`mtime=0`); the committed artifact is copied unchanged. No production code changes or new dependency installations were needed.
