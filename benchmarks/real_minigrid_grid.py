"""Actual MiniGrid Grid.encode/decode snapshot pipeline, not live world storage."""

import argparse
import json
import platform
import sys
import time

import blosc2
import gymnasium as gym
import minigrid
import numpy as np
from minigrid.core.grid import Grid

from tightarray import Array


class GridSnapshot:
    """Only preserves the upstream encoded grid, never full environment state."""

    def __init__(self, encoded, backend):
        if encoded.ndim != 3 or encoded.shape[2] != 3 or encoded.dtype != np.uint8:
            raise ValueError("expected uint8 grid with three channels")
        self.shape = encoded.shape
        self.backend = backend
        if backend == "packed":
            self.data = tuple(
                Array(np.ascontiguousarray(encoded[:, :, i]).ravel(), bits=bits)
                for i, bits in enumerate((4, 3, 2))
            )
            self.payload_bytes = sum(a.nbytes for a in self.data)
            self.python_shallow_bytes = sys.getsizeof(self.data) + sum(
                sys.getsizeof(a) for a in self.data
            )
        elif backend == "numpy":
            self.data = encoded.copy()
            self.payload_bytes = self.data.nbytes
            self.python_shallow_bytes = sys.getsizeof(self.data)
        elif backend in ("blosc-lz4", "blosc-zstd"):
            codec = blosc2.Codec.LZ4 if backend == "blosc-lz4" else blosc2.Codec.ZSTD
            self.data = blosc2.compress2(
                encoded,
                codec=codec,
                clevel=5,
                typesize=1,
                filters=[blosc2.Filter.BITSHUFFLE],
                nthreads=1,
            )
            self.payload_bytes = len(self.data)
            self.python_shallow_bytes = sys.getsizeof(self.data)
        else:
            raise ValueError("unknown backend")

    def encoded(self):
        if self.backend == "packed":
            out = np.empty(self.shape, dtype=np.uint8)
            for i, a in enumerate(self.data):
                out[:, :, i] = np.asarray(a).reshape(self.shape[:2])
            return out
        if self.backend == "numpy":
            return self.data.copy()
        return (
            np.frombuffer(blosc2.decompress2(self.data, nthreads=1), dtype=np.uint8)
            .reshape(self.shape)
            .copy()
        )

    def decoded(self):
        return Grid.decode(self.encoded())


def trace(env_id, steps=20):
    env = gym.make(env_id)
    try:
        env.reset(seed=21)
        rng = np.random.default_rng(21)
        frames = []
        for _ in range(steps):
            # Capture actual full world grid, not the egocentric observation.
            frames.append(env.unwrapped.grid.encode())
            _, _, terminated, truncated, _ = env.step(
                int(rng.integers(env.action_space.n))
            )
            if terminated or truncated:
                env.reset(seed=21)
        return frames
    finally:
        env.close()


def run(repeats=5):
    rows = []
    for env_id in (
        "MiniGrid-Empty-16x16-v0",
        "MiniGrid-DoorKey-16x16-v0",
        "MiniGrid-MultiRoom-N6-v0",
    ):
        frames = trace(env_id)
        # Decode once outside timing to obtain real Grid objects for the pipeline.
        grids = [Grid.decode(frame)[0] for frame in frames]
        for backend in ("numpy", "packed", "blosc-lz4", "blosc-zstd"):
            payload = []
            shallow = []
            for frame in frames:
                snapshot = GridSnapshot(frame, backend)
                np.testing.assert_array_equal(snapshot.encoded(), frame)
                expected, mask = Grid.decode(frame)
                actual, actual_mask = snapshot.decoded()
                np.testing.assert_array_equal(actual.encode(), expected.encode())
                np.testing.assert_array_equal(actual_mask, mask)
                payload.append(snapshot.payload_bytes)
                shallow.append(snapshot.python_shallow_bytes)
            times = []
            storage_times = []
            for _ in range(repeats):
                start = time.perf_counter()
                for grid in grids:
                    snapshot = GridSnapshot(grid.encode(), backend)
                    snapshot.decoded()
                times.append(time.perf_counter() - start)
                start = time.perf_counter()
                for frame in frames:
                    snapshot = GridSnapshot(frame, backend)
                    snapshot.encoded()
                storage_times.append(time.perf_counter() - start)
            rows.append(
                {
                    "env": env_id,
                    "shape": list(frames[0].shape),
                    "frames": len(frames),
                    "backend": backend,
                    "payload_bytes_mean": float(np.mean(payload)),
                    "storage_object_shallow_bytes_mean": float(np.mean(shallow)),
                    "e2e_s": times,
                    "median_e2e_s": float(np.median(times)),
                    "storage_roundtrip_s": storage_times,
                    "median_storage_roundtrip_s": float(np.median(storage_times)),
                    "equal": True,
                }
            )
    return {
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "minigrid": minigrid.__version__,
            "numpy": np.__version__,
            "blosc2": blosc2.__version__,
        },
        "scope": "Actual Grid.encode/storage/Grid.decode roundtrip. Not a live backend, environment checkpoint, or replay buffer. Five warm repeats; payload and shallow sys.getsizeof exclude snapshot wrapper and are not RSS.",
        "results": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="docs/results/real-minigrid-grid.json")
    args = parser.parse_args()
    with open(args.output, "w") as f:
        json.dump(run(), f, indent=2)
        f.write("\n")
