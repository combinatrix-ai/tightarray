"""Synthetic online categorical-field edits; not a real application E2E.

Every update is followed by a read before the next update, so deferred batching
is outside this contract. Blosc2 NDArray uses 64KiB chunks, 8KiB blocks.
"""

import json
import platform
import time
from pathlib import Path

import blosc2
import numpy as np
from numba import njit

from tightarray import Array


def build(source, backend, states):
    if backend in ("numpy", "numpy-numba"):
        return source.copy()
    if backend == "packed":
        return Array(source, bits=(states - 1).bit_length())
    codec = blosc2.Codec.ZSTD if backend == "zstd" else blosc2.Codec.LZ4
    return blosc2.asarray(
        source,
        chunks=(65536,),
        blocks=(8192,),
        cparams={
            "codec": codec,
            "clevel": 5,
            "typesize": 1,
            "nthreads": 1,
            "filters": [blosc2.Filter.BITSHUFFLE],
        },
        dparams={"nthreads": 1},
    )


def edit(data, indices, states):
    checksum = 0
    for i in indices:
        i = int(i)
        value = (int(data[i]) + 1) % states
        data[i] = value
        checksum += int(data[i])
    return checksum


@njit
def compiled_edit(data, indices, states):
    checksum = 0
    for i in indices:
        data[i] = (int(data[i]) + 1) % states
        checksum += int(data[i])
    return checksum


def run(size=2**24, edits=256, repeats=3):
    results = []
    compiled_edit(np.zeros(8, dtype=np.uint8), np.array([0], dtype=np.int64), 8)
    for states, pattern in [(k, p) for k in (8, 32) for p in ("uniform", "blocks256")]:
        source = np.random.default_rng(5).integers(
            0,
            states,
            size if pattern == "uniform" else (size + 255) // 256,
            dtype=np.uint8,
        )
        if pattern == "blocks256":
            source = np.repeat(source, 256)[:size]
        indices = np.random.default_rng(9).integers(0, size, edits, dtype=np.int64)
        expected = source.copy()
        expected_checks = [edit(expected, indices, states) for _ in range(repeats)]
        for backend in ("numpy", "numpy-numba", "packed", "lz4", "zstd"):
            tick = time.perf_counter()
            data = build(source, backend, states)
            build_s = time.perf_counter() - tick
            samples = []
            for check in expected_checks:
                tick = time.perf_counter()
                actual = (
                    compiled_edit(data, indices, states)
                    if backend == "numpy-numba"
                    else edit(data, indices, states)
                )
                samples.append(time.perf_counter() - tick)
                assert actual == check
            materialized = (
                np.frombuffer(data.tobytes(), dtype=np.uint8)
                if backend == "packed"
                else np.asarray(data[:])
            )
            np.testing.assert_array_equal(materialized, expected)
            storage = data.schunk.cbytes if backend in ("lz4", "zstd") else data.nbytes
            results.append(
                {
                    "states": states,
                    "pattern": pattern,
                    "backend": backend,
                    "size": size,
                    "edits": edits,
                    "build_s": build_s,
                    "online_edits_s": samples,
                    "storage_bytes": storage,
                }
            )
            del data, materialized
    return {
        "platform": platform.platform(),
        "numpy": np.__version__,
        "blosc2": blosc2.__version__,
        "jit_excluded": True,
        "results": results,
    }


if __name__ == "__main__":
    result = run()
    Path("docs/results/explore-edits.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    for r in result["results"]:
        print(
            r["states"],
            r["backend"],
            r["storage_bytes"],
            float(np.median(r["online_edits_s"])),
        )
