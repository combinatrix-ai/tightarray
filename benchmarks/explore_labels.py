"""Synthetic 3-D semantic-label storage and materialized patch sampling pilot."""

import argparse
import json
import platform
import time
from functools import lru_cache

import blosc2
import numpy as np
from numba import njit

from tightarray import Array
from tightarray.numba import as_native, specialize


def volume(side, states, structured):
    rng = np.random.default_rng(20260921)
    if not structured:
        return rng.integers(states, size=(side, side, side), dtype=np.uint8)
    # Piecewise-constant regions, not representative clinical data.
    coarse = rng.integers(states, size=((side + 7) // 8,) * 3, dtype=np.uint8)
    return np.repeat(np.repeat(np.repeat(coarse, 8, 0), 8, 1), 8, 2)[
        :side, :side, :side
    ].copy()


@lru_cache(None)
def packed_sampler(bits):
    read, _ = specialize(bits, "packed")

    @njit
    def sample(data, side, origins, width, out):
        for p in range(len(origins)):
            z, y, x = origins[p]
            for dz in range(width):
                for dy in range(width):
                    start = ((z + dz) * side + y + dy) * side + x
                    for dx in range(width):
                        out[p, dz, dy, dx] = read(data, start + dx)

    return sample


@njit
def dense_sampler(data, side, origins, width, out):
    for p in range(len(origins)):
        z, y, x = origins[p]
        for dz in range(width):
            for dy in range(width):
                start = ((z + dz) * side + y + dy) * side + x
                for dx in range(width):
                    out[p, dz, dy, dx] = data[start + dx]


class Store:
    def __init__(self, data, states, backend):
        self.side = data.shape[0]
        self.backend = backend
        if backend in ("numpy", "numpy-numba"):
            self.data = data.copy()
            self.storage_bytes = self.data.nbytes
        elif backend == "tightarray":
            self.bits = (states - 1).bit_length()
            self.data = Array(data.ravel(), bits=self.bits)
            self.native = as_native(self.data)
            self.storage_bytes = self.data.nbytes
        else:
            codec = blosc2.Codec.ZSTD if backend == "blosc-zstd" else blosc2.Codec.LZ4
            chunk = min(32, self.side)
            block = min(8, self.side)
            self.data = blosc2.asarray(
                data,
                chunks=(chunk,) * 3,
                blocks=(block,) * 3,
                cparams={
                    "codec": codec,
                    "clevel": 5,
                    "filters": [blosc2.Filter.BITSHUFFLE],
                    "nthreads": 1,
                },
                dparams={"nthreads": 1},
            )
            self.storage_bytes = self.data.schunk.cbytes

    def sample(self, origins, width):
        if (
            width < 1
            or width > self.side
            or np.any(origins < 0)
            or np.any(origins + width > self.side)
        ):
            raise ValueError("patch lies outside the volume")
        out = np.empty((len(origins), width, width, width), dtype=np.uint8)
        if self.backend == "tightarray":
            packed_sampler(self.bits)(self.native, self.side, origins, width, out)
        elif self.backend == "numpy-numba":
            dense_sampler(self.data.ravel(), self.side, origins, width, out)
        else:
            for i, (z, y, x) in enumerate(origins):
                out[i] = self.data[z : z + width, y : y + width, x : x + width]
        return out


def run(sides=(128, 256), repeats=5):
    rows = []
    rng = np.random.default_rng(1921)
    for side in sides:
        for states in (8, 32):
            for structured in (False, True):
                source = volume(side, states, structured)
                stores = {}
                for backend in (
                    "numpy",
                    "numpy-numba",
                    "tightarray",
                    "blosc-lz4",
                    "blosc-zstd",
                ):
                    start = time.perf_counter()
                    stores[backend] = Store(source, states, backend)
                    stores[backend].build_s = time.perf_counter() - start
                for width in (4, 16, 32):
                    origins = rng.integers(
                        0, side - width + 1, size=(16, 3), dtype=np.int64
                    )
                    expected = stores["numpy"].sample(origins, width)
                    timings = {name: [] for name in stores}
                    first = {}
                    for name, store in stores.items():
                        tick = time.perf_counter()
                        actual = store.sample(origins, width)
                        first[name] = time.perf_counter() - tick
                        np.testing.assert_array_equal(actual, expected)
                    for repeat in range(repeats):
                        names = list(stores)
                        if repeat % 2:
                            names.reverse()
                        for name in names:
                            tick = time.perf_counter()
                            actual = stores[name].sample(origins, width)
                            timings[name].append(time.perf_counter() - tick)
                            np.testing.assert_array_equal(actual, expected)
                    for name, store in stores.items():
                        rows.append(
                            {
                                "side": side,
                                "states": states,
                                "structured": structured,
                                "backend": name,
                                "patch_width": width,
                                "batch": len(origins),
                                "dense_bytes": source.nbytes,
                                "storage_bytes": store.storage_bytes,
                                "build_s": store.build_s,
                                "first_sample_s": first[name],
                                "sample_s": timings[name],
                                "median_sample_s": float(np.median(timings[name])),
                                "equal": True,
                            }
                        )
                print(side, states, structured, flush=True)
    return {
        "scope": "Synthetic resident 3D labels, not application E2E; payload excludes Python objects; output allocation included; warmed timings; first calls may include JIT; single-thread codecs; repeated fixed patches can be cache hot",
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "numpy": np.__version__,
            "blosc2": blosc2.__version__,
        },
        "results": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="docs/results/explore-labels.json")
    parser.add_argument("--sides", nargs="+", type=int, default=[128, 256])
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    with open(args.output, "w") as target:
        json.dump(run(args.sides, args.repeats), target, indent=2)
        target.write("\n")
