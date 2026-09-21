# Real MiniGrid observation replay pilot

The favorable capacity result on synthetic uniformly random observations **does not survive these actual MiniGrid traces**: fixed 4-bit packing halves image payload, but BITSHUFFLE+ZSTD shrinks it to 6.0–7.5% of uint8. Packed still materializes sampled transitions faster than our compressed chunk implementations. NumPy remains fastest.

This executes actual MiniGrid environments and benchmarks replay retention/batch retrieval. It is **not SB3 integration, policy learning, or a training E2E speed claim**.

## Workload and correctness

MiniGrid 3.1.0 / Gymnasium 1.3.0, Python 3.12.8, NumPy 2.5.3, Blosc2 4.13.1, arm64 macOS. Three built-in environments: Empty-8x8, DoorKey-8x8 and FourRooms. Each produces 2,048 transitions using seeded uniform random actions (seed 123), reset seeds incrementing by episode. The episode limit is explicitly shortened to 64 steps; this changes episode length, not observation encoding. No rendering.

The real symbolic image is 7×7×3 uint8: object identity, color, object state. It is not an RGB frame. The replay stores both pre-action and successor images explicitly, together with action, float64 reward, terminated, truncated, direction, successor direction, episode ID, and mission/successor-mission IDs into an immutable string dictionary. The terminal/truncated successor is retained **before reset**, so the next episode's first observation is never substituted for it. All three observation fields (`image`, `direction`, `mission`) are preserved.

Each backend copies the same complete trace. All sampled images and transition metadata match exactly, and mission dictionaries match. Tests verify deterministic generation, episode-boundary IDs, continuity within episodes, partial last compression chunks, duplicate and unordered samples, empty batches, output mutation independence, and out-of-bounds rejection.

## Storage and measurement

- NumPy: contiguous dense transition image tensor.
- packed4: one contiguous tightarray, fixed four bits per image value (all standard MiniGrid codes fit). This avoids a Python object per tiny observation. Per-channel 4/3/2-bit storage is not explored.
- Blosc2 LZ4/ZSTD: both chunks of 32 consecutive transitions and individual-transition chunks (`-single`), level 5, BITSHUFFLE, typesize 1, one thread. Selected 32-transition chunks are decoded once per batch, without a persistent dense cache. Single-transition chunks decompress directly into each output record, avoiding grouping and extra copy overhead. Chunking exploits temporal redundancy but causes decode amplification under random access. The two chunk sizes expose the capacity/random-access tradeoff; this is not an exhaustive compression tuning search.

Each batch contains 64 transitions and includes allocation, image decode, metadata selection and mission-dictionary return. It excludes random-index generation, environment collection, GPU transfer and learning. There are five repeats of 24 batches; tables show median time per batch. Ingest is separately measured once, including validation, allocation and encoding. Recorded raw data also includes environment-collection times.

Image payload is compared separately from common numeric metadata and UTF-8 mission text. Total payload still **excludes Python object/list headers, allocator overhead and process RSS**, and is not measured maximum RAM capacity. Each source image tensor is only 588 KiB; these cache-warm measurements do not establish large-buffer throughput.

## Measured results

| Environment | Backend | Image payload / uint8 | Total payload KiB | Ingest ms | Batch ms |
|---|---|---:|---:|---:|---:|
| MiniGrid-Empty-8x8-v0 | numpy | 100.00% | 630.0 | 0.08 | 0.006 |
| MiniGrid-Empty-8x8-v0 | packed4 | 50.00% | 336.0 | 0.09 | 0.059 |
| MiniGrid-Empty-8x8-v0 | blosc-lz4 | 13.60% | 122.0 | 1.16 | 0.569 |
| MiniGrid-Empty-8x8-v0 | blosc-zstd | 5.97% | 77.1 | 7.43 | 0.741 |
| MiniGrid-Empty-8x8-v0 | blosc-lz4-single | 50.55% | 339.3 | 15.63 | 0.101 |
| MiniGrid-Empty-8x8-v0 | blosc-zstd-single | 43.96% | 300.5 | 22.67 | 0.167 |
| MiniGrid-DoorKey-8x8-v0 | numpy | 100.00% | 630.1 | 0.09 | 0.007 |
| MiniGrid-DoorKey-8x8-v0 | packed4 | 50.00% | 336.1 | 0.09 | 0.060 |
| MiniGrid-DoorKey-8x8-v0 | blosc-lz4 | 15.87% | 135.4 | 1.31 | 0.559 |
| MiniGrid-DoorKey-8x8-v0 | blosc-zstd | 7.48% | 86.0 | 7.98 | 0.750 |
| MiniGrid-DoorKey-8x8-v0 | blosc-lz4-single | 50.75% | 340.5 | 14.88 | 0.100 |
| MiniGrid-DoorKey-8x8-v0 | blosc-zstd-single | 44.14% | 301.6 | 22.64 | 0.159 |
| MiniGrid-FourRooms-v0 | numpy | 100.00% | 630.0 | 0.11 | 0.006 |
| MiniGrid-FourRooms-v0 | packed4 | 50.00% | 336.0 | 0.11 | 0.060 |
| MiniGrid-FourRooms-v0 | blosc-lz4 | 13.24% | 119.9 | 1.11 | 0.567 |
| MiniGrid-FourRooms-v0 | blosc-zstd | 6.08% | 77.8 | 7.94 | 0.715 |
| MiniGrid-FourRooms-v0 | blosc-lz4-single | 48.58% | 327.7 | 15.24 | 0.103 |
| MiniGrid-FourRooms-v0 | blosc-zstd-single | 42.05% | 289.3 | 22.32 | 0.166 |

Packed sampling is around 9–13× faster than the measured 32-transition compressed alternatives, but chunk amplification and Python grouping contribute to that gap. With **single-transition chunks and direct-to-output decompression**, the gap narrows to about 1.7× against LZ4 and 2.7× against ZSTD. Thus the decode advantage survives removal of unrelated-transition decompression, although it is much smaller. NumPy is still about 9–10× faster than packed.

Single-transition ZSTD image payload is 42.0–44.1% of dense, still smaller than packed's 50%. Single-transition LZ4 is 48.6–50.8%, straddling packed. Consequently packed offers a measured intermediate point between NumPy and compressed storage, but is not a universal winner. Batch-native codecs and chunk tuning could change that frontier.

**Conclusion:** these real low-entropy boards support fixed packing as a predictable-capacity/cheap-sampling option, but they do not support a best-capacity claim. General compression is the clear payload winner. Finding a stronger packing niche requires actual high-entropy narrow categorical observations or latency-sensitive access where its explicit tradeoff is worthwhile.

## Reproduce

```sh
python -m benchmarks.real_minigrid_replay
python -m pytest -q tests/test_real_minigrid_replay.py
```

Dependencies: tightarray, NumPy, MiniGrid, Gymnasium and Blosc2. [Raw results](results/real-minigrid-replay.json). Source environments: [MiniGrid repository](https://github.com/Farama-Foundation/Minigrid); the executed package version is captured in the JSON.
