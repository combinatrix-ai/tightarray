# Discrete observation replay storage pilot

This is a synthetic storage/decode experiment, **not Stable Baselines3 integration or training E2E**. It tests a necessary part of discrete-board replay: retain observations and materialize randomly sampled dense batches. Actions, rewards, next-observation sharing, ring-buffer replacement, GPU transfers, and learning are not measured.

## Reproduce

```sh
python -m benchmarks.explore_replay
python -m pytest -q tests/test_explore_replay.py
```

Install the repository and NumPy/Blosc2 in the environment first. The recorded run used Python 3.12.8, NumPy 2.5.3, Blosc2 4.13.1 on arm64 macOS. See [raw measurements](results/explore-replay.json).

Each case contains 2,048 independent 64×64 uint8 observations (8 MiB dense). There are 8 or 32 possible values. `uniform` assigns independent uniformly random codes; `blocks8` repeats each random code across an 8×8 spatial block. These bracket entropy rather than model real environment dynamics. Every record is compressed separately for direct random observation access. Blosc2 uses LZ4 or ZSTD, level 5, BITSHUFFLE, typesize 1 and one thread; there is no JIT. Larger compression chunks could improve compression but require decoding unrelated observations, and are not tested here.

Ingest includes validation, allocation and encoding from an existing dense source; it is a single timing. Batch timing includes index validation, allocation, decompression and a returned dense batch of 64 observations (256 KiB). It excludes index RNG, environment generation and training. Reported batch time is the median of five repeats, each containing 24 batches. All sampled batches were checked byte-for-byte before timing, including duplicate indices. Repeated batches are cache-warm; this small experiment does not establish performance for RAM-sized replay.

## Results

| States | Input | Backend | Payload / uint8 | Ingest ms | Batch ms |
|---|---|---|---:|---:|---:|
| 8 | uniform | numpy | 100.00% | 1.3 | 0.025 |
| 8 | uniform | packed | 37.50% | 2.2 | 0.099 |
| 8 | uniform | blosc-lz4 | 39.28% | 21.8 | 0.261 |
| 8 | uniform | blosc-zstd | 38.99% | 38.3 | 0.302 |
| 8 | blocks8 | numpy | 100.00% | 0.3 | 0.020 |
| 8 | blocks8 | packed | 37.50% | 2.1 | 0.097 |
| 8 | blocks8 | blosc-lz4 | 8.46% | 21.9 | 0.293 |
| 8 | blocks8 | blosc-zstd | 4.05% | 104.2 | 0.353 |
| 32 | uniform | numpy | 100.00% | 0.4 | 0.022 |
| 32 | uniform | packed | 62.50% | 2.3 | 0.102 |
| 32 | uniform | blosc-lz4 | 64.36% | 21.8 | 0.259 |
| 32 | uniform | blosc-zstd | 63.99% | 43.1 | 0.300 |
| 32 | blocks8 | numpy | 100.00% | 0.3 | 0.021 |
| 32 | blocks8 | packed | 62.50% | 2.4 | 0.101 |
| 32 | blocks8 | blosc-lz4 | 12.93% | 23.5 | 0.301 |
| 32 | blocks8 | blosc-zstd | 5.38% | 190.5 | 0.351 |

For uniformly distributed narrow codes, tightarray uses slightly less payload than both compressed baselines, while sampled batches decode approximately 2.6–3.1× faster. This is a plausible niche: entropy is already close to the fixed bit width, so compression adds headers and work with little further reduction. NumPy still decodes about 4–5× faster than packed here.

For spatially structured observations, ZSTD uses dramatically less space (about 4–5% of dense) than fixed packing (37.5–62.5%). Packed still samples faster, but **does not win capacity** against general compression on this input.

These memory figures are stored payload only. They exclude Python list and object headers, allocator overhead, input observations, output batches and process runtime; compressed payload includes Blosc chunk headers, packed payload includes word padding. They must not be read as measured peak RSS or maximum experience capacity. Per-observation object overhead matters more for smaller boards.

## Decision

The strongest next candidate is discrete observations with high entropy within a small known alphabet, where sampling throughput matters and fixed storage size is useful. A real replay adapter should compare identical experience capacities and identical RAM budgets, use actual environment traces, test large replay buffers and sampling locality, and measure training E2E. Low-entropy label maps should retain Blosc2 as a serious baseline, not assume fixed packing is the best capacity representation.
