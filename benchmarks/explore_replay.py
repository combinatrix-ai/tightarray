"""Synthetic discrete observation replay storage; not an RL training benchmark."""

import argparse
import json
import platform
import statistics
import time
from pathlib import Path

import blosc2
import numpy as np

from tightarray import Array

BACKENDS = ("numpy", "packed", "blosc-lz4", "blosc-zstd")


def observations(count, side, states, structured, seed=123):
    rng = np.random.default_rng(seed)
    if structured:
        coarse = rng.integers(
            0, states, (count, (side + 7) // 8, (side + 7) // 8), dtype=np.uint8
        )
        return np.ascontiguousarray(
            coarse.repeat(8, axis=1).repeat(8, axis=2)[:, :side, :side]
        )
    return rng.integers(0, states, (count, side, side), dtype=np.uint8)


class ReplayStorage:
    """Independent observations allow random batches without decoding neighbors."""

    def __init__(self, data, states, backend):
        if backend not in BACKENDS or states not in (8, 32):
            raise ValueError("unsupported backend or state count")
        if data.dtype != np.uint8 or data.ndim != 3 or data.size == 0:
            raise ValueError("expected nonempty uint8 observation stack")
        if int(data.max()) >= states:
            raise ValueError("value exceeds states")
        self.shape = data.shape
        self.backend = backend
        self.bits = (states - 1).bit_length()
        if backend == "numpy":
            self.data = data.copy()
        elif backend == "packed":
            self.data = [Array(row.reshape(-1), bits=self.bits) for row in data]
        else:
            codec = blosc2.Codec.LZ4 if backend == "blosc-lz4" else blosc2.Codec.ZSTD
            self.data = [
                blosc2.compress2(
                    row,
                    codec=codec,
                    clevel=5,
                    typesize=1,
                    nthreads=1,
                    filters=[blosc2.Filter.NOFILTER] * 5 + [blosc2.Filter.BITSHUFFLE],
                )
                for row in data
            ]

    @property
    def payload_bytes(self):
        if self.backend == "numpy":
            return self.data.nbytes
        if self.backend == "packed":
            return sum(row.nbytes for row in self.data)
        return sum(len(row) for row in self.data)

    def sample(self, indices):
        indices = np.asarray(indices)
        if indices.ndim != 1 or indices.dtype.kind not in "iu":
            raise ValueError("expected integer index vector")
        if np.any(indices < 0) or np.any(indices >= self.shape[0]):
            raise IndexError("observation index out of bounds")
        if self.backend == "numpy":
            return self.data[indices]
        out = np.empty((len(indices), *self.shape[1:]), dtype=np.uint8)
        for pos, index in enumerate(indices):
            row = self.data[int(index)]
            if self.backend == "packed":
                out[pos] = np.frombuffer(row.tobytes(), dtype=np.uint8).reshape(
                    self.shape[1:]
                )
            else:
                blosc2.decompress2(row, dst=out[pos], nthreads=1)
        return out


def run(count=2048, side=64, batch=64, rounds=24, repeats=5):
    records = []
    rng = np.random.default_rng(456)
    indices = rng.integers(0, count, (rounds, batch))
    for states in (8, 32):
        for structured in (False, True):
            data = observations(count, side, states, structured)
            for backend in BACKENDS:
                start = time.perf_counter()
                storage = ReplayStorage(data, states, backend)
                build_ms = (time.perf_counter() - start) * 1000
                # Validate every sampled batch including duplicates before timing.
                for ids in indices:
                    np.testing.assert_array_equal(storage.sample(ids), data[ids])
                timings = []
                for _ in range(repeats):
                    start = time.perf_counter()
                    for ids in indices:
                        result = storage.sample(ids)
                    timings.append((time.perf_counter() - start) * 1000 / rounds)
                records.append(
                    {
                        "states": states,
                        "distribution": "blocks8" if structured else "uniform",
                        "backend": backend,
                        "observations": count,
                        "shape": [side, side],
                        "batch": batch,
                        "dense_bytes": data.nbytes,
                        "payload_bytes": storage.payload_bytes,
                        "payload_ratio": storage.payload_bytes / data.nbytes,
                        "build_ms": build_ms,
                        "batch_ms_median": statistics.median(timings),
                        "batch_ms_samples": timings,
                        "exact": True,
                        "batch_output_bytes": result.nbytes,
                    }
                )
                del storage
    return {
        "metadata": {
            "python": platform.python_version(),
            "machine": platform.machine(),
            "numpy": np.__version__,
            "blosc2": blosc2.__version__,
            "rounds": rounds,
            "repeats": repeats,
            "seed_data": 123,
            "seed_indices": 456,
            "scope": "Synthetic storage and batch decode, not SB3 training E2E",
            "memory": "Payload only; excludes Python objects, source input, allocator and output batch",
            "compression": "Per observation, clevel=5, BITSHUFFLE, typesize=1, nthreads=1",
        },
        "records": records,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("docs/results/explore-replay.json")
    )
    args = parser.parse_args()
    result = run()
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    for row in result["records"]:
        print(
            row["states"],
            row["distribution"],
            row["backend"],
            round(row["payload_ratio"], 4),
            round(row["batch_ms_median"], 3),
        )
