"""Actual MiniGrid traces, replay retention and batch retrieval; no training."""

import argparse
import json
import platform
import statistics
import time
from pathlib import Path

import blosc2
import gymnasium as gym
import minigrid
import numpy as np

from tightarray import Array

ENVIRONMENTS = (
    "MiniGrid-Empty-8x8-v0",
    "MiniGrid-DoorKey-8x8-v0",
    "MiniGrid-FourRooms-v0",
)
BACKENDS = (
    "numpy",
    "packed4",
    "blosc-lz4",
    "blosc-zstd",
    "blosc-lz4-single",
    "blosc-zstd-single",
)
META = np.dtype(
    [
        ("action", "u1"),
        ("reward", "f8"),
        ("terminated", "?"),
        ("truncated", "?"),
        ("direction", "u1"),
        ("next_direction", "u1"),
        ("mission", "u2"),
        ("next_mission", "u2"),
        ("episode", "u4"),
    ]
)


def collect(env_id, count=2048, seed=123):
    """Store explicit pre/post observations before resetting terminated episodes."""
    env = gym.make(env_id, max_episode_steps=64)
    rng = np.random.default_rng(seed)
    observation, _ = env.reset(seed=seed)
    images = np.empty((count, 2, *observation["image"].shape), dtype=np.uint8)
    metadata = np.empty(count, dtype=META)
    missions = []
    episode = 0

    def mission_id(text):
        if text not in missions:
            missions.append(text)
        return missions.index(text)

    try:
        for i in range(count):
            action = int(rng.integers(env.action_space.n))
            successor, reward, terminated, truncated, _ = env.step(action)
            images[i, 0] = observation["image"]
            images[i, 1] = successor["image"]
            metadata[i] = (
                action,
                reward,
                terminated,
                truncated,
                observation["direction"],
                successor["direction"],
                mission_id(observation["mission"]),
                mission_id(successor["mission"]),
                episode,
            )
            if terminated or truncated:
                episode += 1
                observation, _ = env.reset(seed=seed + episode)
            else:
                observation = successor
    finally:
        env.close()
    return images, metadata, tuple(missions)


class TraceReplay:
    def __init__(self, images, metadata, missions, backend, chunk=32):
        if (
            backend not in BACKENDS
            or images.dtype != np.uint8
            or int(images.max()) > 15
        ):
            raise ValueError("unsupported backend or MiniGrid encoding")
        if len(metadata) != len(images) or chunk < 1:
            raise ValueError("invalid metadata or chunk length")
        self.shape = images.shape
        self.backend = backend
        self.chunk = 1 if backend.endswith("-single") else chunk
        chunk = self.chunk
        self.record_size = int(np.prod(images.shape[1:]))
        self.metadata = metadata.copy()
        self.missions = tuple(missions)
        if backend == "numpy":
            self.images = images.copy()
        elif backend == "packed4":
            self.images = Array(images.reshape(-1), bits=4)
        else:
            codec = (
                blosc2.Codec.LZ4
                if backend.startswith("blosc-lz4")
                else blosc2.Codec.ZSTD
            )
            self.images = [
                blosc2.compress2(
                    images[i : i + chunk],
                    codec=codec,
                    clevel=5,
                    typesize=1,
                    nthreads=1,
                    filters=[blosc2.Filter.NOFILTER] * 5 + [blosc2.Filter.BITSHUFFLE],
                )
                for i in range(0, len(images), chunk)
            ]

    @property
    def image_bytes(self):
        return (
            self.images.nbytes
            if self.backend in ("numpy", "packed4")
            else sum(map(len, self.images))
        )

    @property
    def payload_bytes(self):
        return (
            self.image_bytes
            + self.metadata.nbytes
            + sum(len(s.encode()) for s in self.missions)
        )

    def sample(self, ids):
        ids = np.asarray(ids)
        if ids.ndim != 1 or ids.dtype.kind not in "iu":
            raise ValueError("integer vector required")
        if np.any(ids < 0) or np.any(ids >= self.shape[0]):
            raise IndexError("transition index out of range")
        if self.backend == "numpy":
            result = self.images[ids]
        else:
            result = np.empty((len(ids), *self.shape[1:]), dtype=np.uint8)
            if self.backend == "packed4":
                for pos, index in enumerate(ids):
                    begin = int(index) * self.record_size
                    result[pos] = np.frombuffer(
                        self.images[begin : begin + self.record_size].tobytes(),
                        dtype=np.uint8,
                    ).reshape(self.shape[1:])
            elif self.chunk == 1:
                for pos, index in enumerate(ids):
                    blosc2.decompress2(
                        self.images[int(index)], dst=result[pos], nthreads=1
                    )
            else:
                # Decompress each selected chunk once per batch; never persist a dense cache.
                for group in np.unique(ids // self.chunk):
                    positions = np.flatnonzero(ids // self.chunk == group)
                    raw = blosc2.decompress2(self.images[int(group)], nthreads=1)
                    decoded = np.frombuffer(raw, dtype=np.uint8).reshape(
                        (-1, *self.shape[1:])
                    )
                    result[positions] = decoded[ids[positions] % self.chunk]
        return result, self.metadata[ids], self.missions


def run(count=2048, batch=64, repeats=5, rounds=24):
    records = []
    rng = np.random.default_rng(456)
    ids = rng.integers(count, size=(rounds, batch))
    for env_id in ENVIRONMENTS:
        start = time.perf_counter()
        images, metadata, missions = collect(env_id, count)
        collection_ms = (time.perf_counter() - start) * 1000
        for backend in BACKENDS:
            start = time.perf_counter()
            replay = TraceReplay(images, metadata, missions, backend)
            build_ms = (time.perf_counter() - start) * 1000
            for indices in ids:
                actual, meta, texts = replay.sample(indices)
                np.testing.assert_array_equal(actual, images[indices])
                np.testing.assert_array_equal(meta, metadata[indices])
                assert texts == missions
            samples = []
            for _ in range(repeats):
                start = time.perf_counter()
                for indices in ids:
                    replay.sample(indices)
                samples.append((time.perf_counter() - start) * 1000 / rounds)
            records.append(
                {
                    "env": env_id,
                    "backend": backend,
                    "transitions": count,
                    "image_shape": list(images.shape[2:]),
                    "chunk_transitions": replay.chunk
                    if backend.startswith("blosc")
                    else None,
                    "image_bytes": replay.image_bytes,
                    "dense_image_bytes": images.nbytes,
                    "total_payload_bytes": replay.payload_bytes,
                    "common_metadata_bytes": metadata.nbytes,
                    "terminated": int(metadata["terminated"].sum()),
                    "truncated": int(metadata["truncated"].sum()),
                    "mission_count": len(missions),
                    "collection_ms": collection_ms,
                    "build_ms": build_ms,
                    "batch_ms": statistics.median(samples),
                    "batch_samples_ms": samples,
                    "exact": True,
                }
            )
            del replay
    return {
        "metadata": {
            "python": platform.python_version(),
            "machine": platform.machine(),
            "minigrid": minigrid.__version__,
            "gymnasium": gym.__version__,
            "numpy": np.__version__,
            "blosc2": blosc2.__version__,
            "batch": batch,
            "rounds": rounds,
            "repeats": repeats,
            "policy": "seeded uniform random actions; max_episode_steps=64",
            "seed": 123,
            "compression": "32 transitions/chunk or 1 for -single, clevel5, BITSHUFFLE, typesize1, nthreads1",
            "scope": "actual environment observations; storage and sampled transitions, not training E2E",
            "memory": "payload only, not process RSS",
        },
        "records": records,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("docs/results/real-minigrid-replay.json")
    )
    args = parser.parse_args()
    result = run()
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    for r in result["records"]:
        print(r["env"], r["backend"], r["image_bytes"], round(r["batch_ms"], 3))
