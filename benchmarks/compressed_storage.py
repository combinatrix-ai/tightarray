"""Paired chunk/cache storage benchmark. Payload accounting, never process RSS."""

import argparse
import hashlib
import json
import platform
import statistics
import sys
import time
from collections import OrderedDict
from dataclasses import asdict
from pathlib import Path

import blosc2
import numpy as np

from tightarray import Array

BACKENDS = (
    "numpy",
    "packed",
    "palette-none",
    "palette-lz4",
    "palette-zstd",
    "dense-lz4",
    "dense-zstd",
)
CASES = ("random8", "random32", "local-two", "uniform-chunks", "runs32", "rare-spikes")


def dataset(name, size, chunk, seed=812):
    rng = np.random.default_rng(seed)
    if name == "random8":
        return rng.integers(8, size=size, dtype=np.uint8)
    if name == "random32":
        return rng.integers(32, size=size, dtype=np.uint8)
    if name == "local-two":
        out = np.empty(size, dtype=np.uint8)
        for start in range(0, size, chunk):
            labels = rng.choice(np.arange(128, 256, dtype=np.uint8), 2, replace=False)
            out[start : start + chunk] = labels[
                rng.integers(2, size=min(chunk, size - start))
            ]
        return out
    if name == "uniform-chunks":
        return np.repeat(
            rng.integers(256, size=(size + chunk - 1) // chunk, dtype=np.uint8), chunk
        )[:size].copy()
    if name == "runs32":
        return np.repeat(rng.integers(32, size=(size + 31) // 32, dtype=np.uint8), 32)[
            :size
        ].copy()
    out = np.zeros(size, dtype=np.uint8)
    chosen = rng.choice(size, max(1, size // 1000), replace=False)
    out[chosen] = rng.integers(1, 256, size=len(chosen), dtype=np.uint8)
    return out


class DenseLRU:
    """Blosc cold chunks plus byte-bounded decoded uint8 LRU, with dirty writeback."""

    def __init__(self, values, chunk, budget, codec):
        self.chunk, self.budget = chunk, budget
        self.codec = blosc2.Codec.LZ4 if codec == "lz4" else blosc2.Codec.ZSTD
        self.cold = [
            self.encode(values[i : i + chunk]) for i in range(0, len(values), chunk)
        ]
        self.cache = OrderedDict()
        self.dirty = set()
        self.used = self.hits = self.misses = self.evictions = 0

    def encode(self, data):
        return blosc2.compress2(
            data,
            codec=self.codec,
            clevel=5,
            typesize=1,
            nthreads=1,
            filters=[blosc2.Filter.NOFILTER] * 5 + [blosc2.Filter.BITSHUFFLE],
        )

    def get_chunk(self, index):
        if index in self.cache:
            self.hits += 1
            self.cache.move_to_end(index)
            return self.cache[index]
        self.misses += 1
        value = bytearray(blosc2.decompress2(self.cold[index], nthreads=1))
        if len(value) <= self.budget:
            while self.used + len(value) > self.budget:
                old, data = self.cache.popitem(last=False)
                if old in self.dirty:
                    self.cold[old] = self.encode(data)
                    self.dirty.remove(old)
                self.used -= len(data)
                self.evictions += 1
            self.cache[index] = value
            self.used += len(value)
        return value

    def __getitem__(self, index):
        return self.get_chunk(index // self.chunk)[index % self.chunk]

    def __setitem__(self, index, value):
        key = index // self.chunk
        data = self.get_chunk(key)
        data[index % self.chunk] = value
        if key in self.cache:
            self.dirty.add(key)
        else:
            self.cold[key] = self.encode(data)

    def read(self, start, stop):
        output = bytearray()
        while start < stop:
            key, offset = divmod(start, self.chunk)
            count = min(stop - start, self.chunk - offset)
            output.extend(self.get_chunk(key)[offset : offset + count])
            start += count
        return bytes(output)

    def flush(self):
        for key in self.dirty:
            self.cold[key] = self.encode(self.cache[key])
        self.dirty.clear()

    def clear_cache(self):
        self.flush()
        self.cache.clear()
        self.used = 0

    def info(self):
        stored = sum(map(len, self.cold))
        seen = set()

        def owned(value):
            if id(value) in seen:
                return 0
            seen.add(id(value))
            total = sys.getsizeof(value)
            if isinstance(value, dict):
                total += sum(owned(k) + owned(v) for k, v in value.items())
            elif isinstance(value, (list, tuple, set)):
                total += sum(owned(item) for item in value)
            return total

        retained = owned(self) + sys.getsizeof(self.__dict__)
        retained += sum(
            owned(value) for key, value in self.__dict__.items() if key != "codec"
        )
        return {
            "stored_bytes": stored,
            "cache_bytes": self.used,
            "owned_bytes": retained,
            "cache_hits": self.hits,
            "cache_misses": self.misses,
            "evictions": self.evictions,
        }


class Store:
    def __init__(self, data, backend, chunk, budget):
        self.backend = backend
        if backend == "numpy":
            self.data = data.copy()
        elif backend == "packed":
            self.data = Array(data, bits=max(1, int(data.max()).bit_length()))
        elif backend.startswith("dense-"):
            self.data = DenseLRU(data, chunk, budget, backend.split("-")[1])
        else:
            from tightarray.compressed import CompressedArray

            self.data = CompressedArray(
                data,
                chunk_size=chunk,
                cache_bytes=budget,
                codec=backend.split("-")[1],
                palette=True,
            )

    def read(self, start, stop):
        if self.backend in ("numpy", "packed"):
            return self.data[start:stop].tobytes()
        return self.data.read(start, stop)

    def clear(self):
        if self.backend not in ("numpy", "packed"):
            self.data.clear_cache()

    def flush(self):
        if self.backend not in ("numpy", "packed"):
            self.data.flush()

    def info(self):
        if self.backend in ("numpy", "packed"):
            n = self.data.nbytes
            return {
                "stored_bytes": n,
                "cache_bytes": 0,
                "owned_bytes": sys.getsizeof(self.data),
                "cache_hits": 0,
                "cache_misses": 0,
                "evictions": 0,
            }
        if self.backend.startswith("dense-"):
            return self.data.info()
        return asdict(self.data.storage_info())


def traces(data, chunk, count=256):
    rng = np.random.default_rng(914)
    chunks = (len(data) + chunk - 1) // chunk
    selected = rng.choice(chunks, min(8, chunks), replace=False)
    local = np.minimum(
        selected[rng.integers(len(selected), size=count)] * chunk
        + rng.integers(chunk, size=count),
        len(data) - 1,
    )
    medium_selected = rng.choice(chunks, min(32, chunks), replace=False)
    medium = np.minimum(
        medium_selected[rng.integers(len(medium_selected), size=count)] * chunk
        + rng.integers(chunk, size=count),
        len(data) - 1,
    )
    global_ids = rng.integers(len(data), size=count)
    blocks = rng.integers(len(data) - 63, size=count // 4)
    updates = rng.integers(len(data), size=count // 4)
    alphabet = np.unique(data)
    values = alphabet[rng.integers(len(alphabet), size=count // 4)]
    return (
        local.tolist(),
        medium.tolist(),
        global_ids.tolist(),
        blocks.tolist(),
        updates.tolist(),
        values.tolist(),
    )


def trial(data, backend, chunk, budget, operations):
    start = time.perf_counter()
    store = Store(data, backend, chunk, budget)
    build = time.perf_counter() - start
    store.flush()
    store.clear()
    initial_info = store.info()
    # Full verification is outside timing and followed by cache reset.
    assert store.read(0, len(data)) == data.tobytes()
    store.clear()
    local, medium, global_ids, blocks, updates, values = operations
    result = {"build_ms": build * 1000, "initial_storage": initial_info}
    for label, ids in (
        ("local_scalar", local),
        ("medium_scalar", medium),
        ("global_scalar", global_ids),
        ("read64", blocks),
    ):
        store.clear()
        if label in ("local_scalar", "medium_scalar"):
            # Prewarm the exact local working set, equally for all cache backends.
            for i in ids:
                store.data[i]
        before = store.info()
        start = time.perf_counter()
        if label == "read64":
            actual = [store.read(i, i + 64) for i in ids]
        else:
            actual = [int(store.data[i]) for i in ids]
        elapsed = time.perf_counter() - start
        after = store.info()
        expected = (
            [data[i : i + 64].tobytes() for i in ids]
            if label == "read64"
            else [int(data[i]) for i in ids]
        )
        assert actual == expected
        result[label + "_ms"] = elapsed * 1000
        result[label + "_cache"] = {
            key: after[key] - before[key]
            for key in ("cache_hits", "cache_misses", "evictions")
        }
        result[label + "_storage"] = after
    store.clear()
    start = time.perf_counter()
    for i, value in zip(updates, values, strict=True):
        store.data[i] = value
    store.flush()
    result["updates_flush_ms"] = (time.perf_counter() - start) * 1000
    result["updated_storage"] = store.info()
    expected = data.copy()
    for i, value in zip(updates, values, strict=True):
        expected[i] = value
    store.clear()
    assert store.read(0, len(data)) == expected.tobytes()
    assert store.info()["cache_bytes"] <= budget or backend in ("numpy", "packed")
    return result


def source_hashes():
    root = Path(__file__).resolve().parents[1]
    return {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in (
            "tightarray/compressed.py",
            "tightarray/_compressed.h",
            "tightarray/_compressed_hot.h",
            "tightarray/_compressed_rle.h",
            "tightarray/_core.c",
            "setup.py",
            "benchmarks/compressed_storage.py",
        )
    }


def run(size=1 << 20, repeats=3, sweep=True):
    provenance = source_hashes()
    matrix = [(name, 4096, 65536) for name in CASES]
    if sweep:
        matrix += [
            (name, chunk, 65536)
            for name in ("random8", "local-two")
            for chunk in (1024, 16384)
        ]
        matrix += [(name, 4096, 0) for name in ("random8", "uniform-chunks")]
    output = []
    for case_index, (name, chunk, budget) in enumerate(matrix):
        data = dataset(name, size, 4096)  # Same source data across chunk-size sweep.
        operations = traces(data, chunk)
        runs = {backend: [] for backend in BACKENDS}
        for repeat in range(repeats):
            shift = (case_index + repeat) % len(BACKENDS)
            order = BACKENDS[shift:] + BACKENDS[:shift]
            for backend in order:
                runs[backend].append(trial(data, backend, chunk, budget, operations))
        for backend, results in runs.items():
            output.append(
                {
                    "case": name,
                    "backend": backend,
                    "chunk_size": chunk,
                    "cache_budget": budget,
                    "logical_bytes": size,
                    "median_ms": {
                        key: statistics.median(r[key] for r in results)
                        for key in (
                            "build_ms",
                            "local_scalar_ms",
                            "medium_scalar_ms",
                            "global_scalar_ms",
                            "read64_ms",
                            "updates_flush_ms",
                        )
                    },
                    "samples": results,
                    "exact": True,
                }
            )
        print(name, chunk, budget, "complete", flush=True)
    assert source_hashes() == provenance, "source changed during benchmark"
    return {
        "metadata": {
            "source_sha256": provenance,
            "python": platform.python_version(),
            "numpy": np.__version__,
            "blosc2": blosc2.__version__,
            "machine": platform.machine(),
            "repeats": repeats,
            "scalar_reads": 256,
            "source_region_bytes": 4096,
            "local_working_set_chunks": 8,
            "medium_working_set_chunks": 32,
            "block_reads": 64,
            "block_bytes": 64,
            "updates": 64,
            "update_values": "uniformly selected from observed alphabet (can expand local palettes)",
            "memory": "stored_bytes/cache_bytes are payload; owned_bytes is sys.getsizeof retained graph including metadata, excluding Store wrapper/shared runtime; neither is RSS or transient scratch",
            "uniform_storage": "zero stored payload does not mean zero memory: constant values/chunk records are excluded from stored_bytes but included in owned_bytes",
            "order": "backend order rotated by case and repeat",
            "threads": 1,
            "seeds": {"dataset": 812, "traces": 914},
            "dense_compression": "clevel5 BITSHUFFLE typesize1, dirty LRU byte budget",
        },
        "records": output,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("docs/compressed-storage-results.json")
    )
    parser.add_argument("--size", type=int, default=1 << 20)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--no-sweep", action="store_true")
    args = parser.parse_args()
    results = run(args.size, args.repeats, not args.no_sweep)
    args.output.write_text(json.dumps(results, indent=2) + "\n")
