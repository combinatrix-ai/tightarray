"""Diploid biallelic genotype storage and real scikit-allel query pilot."""

import argparse
import json
import platform
import time
from statistics import median

import allel
import blosc2
import numpy as np
from numba import njit

from tightarray import Array
from tightarray.numba import as_native, specialize

read, _write = specialize(2, "packed")


@njit
def packed_counts(a, start, variants, samples):
    out = np.zeros((variants, 3), dtype=np.int64)
    for v in range(variants):
        for s in range(samples * 2):
            out[v, read(a, (v + start) * samples * 2 + s)] += 1
    return out


@njit
def dense_counts(a, start, variants, samples):
    out = np.zeros((variants, 3), dtype=np.int64)
    for v in range(variants):
        for s in range(samples):
            for p in range(2):
                out[v, int(a[start + v, s, p]) + 1] += 1
    return out


def make_data(variants, samples, distribution, seed=20260921):
    rng = np.random.default_rng(seed)
    data = np.empty((variants, samples, 2), dtype=np.int8)
    # Chunk generation bounds temporary allocation; no large float tensor.
    for start in range(0, variants, 64):
        end = min(start + 64, variants)
        freq = (
            rng.uniform(0.05, 0.5, (end - start, 1, 1))
            if distribution == "common"
            else rng.uniform(0.0001, 0.01, (end - start, 1, 1))
        )
        draw = rng.random((end - start, samples, 2))
        data[start:end] = (draw < freq).astype(np.int8)
        data[start:end][draw > 0.99] = -1
    return data


class Store:
    def __init__(self, data, backend):
        if data.ndim != 3 or data.shape[2] != 2 or data.dtype != np.int8:
            raise ValueError("Expected diploid int8 genotype array")
        if data.size and (data.min() < -1 or data.max() > 1):
            raise ValueError("Only biallelic calls and -1 missing are supported")
        self.shape = data.shape
        self.backend = backend
        if backend == "numpy":
            self.data = data.copy()
        elif backend == "allel-packed":
            self.data = allel.GenotypeArray(data).to_packed()
        elif backend == "tightarray":
            self.data = Array((data.reshape(-1) + 1).astype(np.uint8), bits=2)
            self.native = as_native(self.data)
        elif backend == "blosc2":
            self.data = [
                blosc2.compress2(
                    data[start : start + 128],
                    codec=blosc2.Codec.ZSTD,
                    clevel=5,
                    typesize=1,
                    nthreads=1,
                    filters=[blosc2.Filter.NOFILTER] * 5 + [blosc2.Filter.BITSHUFFLE],
                )
                for start in range(0, len(data), 128)
            ]
        else:
            raise ValueError(backend)

    @property
    def nbytes(self):
        if self.backend == "blosc2":
            return sum(map(len, self.data))
        return self.data.nbytes

    def region(self, start, count):
        if self.backend == "numpy":
            return self.data[start : start + count]
        if self.backend == "allel-packed":
            return allel.GenotypeArray.from_packed(
                self.data[start : start + count]
            ).values
        if self.backend == "blosc2":
            chunks = [
                np.frombuffer(
                    blosc2.decompress2(self.data[i], nthreads=1), dtype=np.int8
                ).reshape(-1, self.shape[1], 2)
                for i in range(start // 128, (start + count - 1) // 128 + 1)
            ]
            decoded = np.concatenate(chunks)
            return decoded[start % 128 : start % 128 + count]
        stride = self.shape[1] * 2
        return (
            np.asarray(self.data[start * stride : (start + count) * stride])
            .astype(np.int8)
            .reshape(count, self.shape[1], 2)
            - 1
        )

    def query(self, start, count, fused=False):
        if fused and self.backend == "tightarray":
            return packed_counts(self.native, start, count, self.shape[1])
        if fused and self.backend == "numpy":
            return dense_counts(self.data, start, count, self.shape[1])
        region = self.region(start, count)
        counts = allel.GenotypeArray(region).count_alleles(max_allele=1).values
        missing = (region < 0).sum(axis=(1, 2))
        return np.column_stack((missing, counts))


def timed(call, repeats):
    durations = []
    for _ in range(repeats):
        tick = time.perf_counter()
        call()
        durations.append(time.perf_counter() - tick)
    return median(durations)


def run(variants=8192, samples=1024, repeats=3):
    results = []
    # Compile small inputs; report JIT separately and never hide it in first-use claims.
    warm = np.zeros((2, 2, 2), dtype=np.int8)
    jit = {}
    for name in ("numpy", "tightarray"):
        store = Store(warm, name)
        tick = time.perf_counter()
        store.query(0, 2, True)
        jit[name] = time.perf_counter() - tick
    for distribution in ("common", "rare"):
        data = make_data(variants, samples, distribution)
        starts = np.random.default_rng(82).integers(0, variants - 64 + 1, 32).tolist()
        reference = Store(data, "numpy")
        expected = [reference.query(start, 64) for start in starts]
        expected_scan = reference.query(0, variants)
        for name in ("numpy", "allel-packed", "tightarray", "blosc2"):
            tick = time.perf_counter()
            store = Store(data, name)
            build = time.perf_counter() - tick
            for start in starts:
                np.testing.assert_array_equal(
                    store.region(start, 64), data[start : start + 64]
                )
            for fused in [False, True] if name in ("numpy", "tightarray") else [False]:

                def random_queries(store=store, fused=fused, starts=starts):
                    return [store.query(start, 64, fused) for start in starts]

                def scan(store=store, fused=fused):
                    return np.concatenate(
                        [
                            store.query(start, min(128, variants - start), fused)
                            for start in range(0, variants, 128)
                        ]
                    )

                for got, want in zip(random_queries(), expected):
                    np.testing.assert_array_equal(got, want)
                np.testing.assert_array_equal(scan(), expected_scan)
                row = {
                    "distribution": distribution,
                    "backend": name,
                    "query": "fused-numba" if fused else "extract-and-scikit-allel",
                    "variants": variants,
                    "samples": samples,
                    "payload_bytes": store.nbytes,
                    "build_s": build,
                    "random_32x64_s": timed(random_queries, repeats),
                    "full_scan_s": timed(scan, repeats),
                    "exact": True,
                }
                results.append(row)
                print(row, flush=True)
    return {
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "numpy": np.__version__,
            "scikit_allel": allel.__version__,
            "blosc2": blosc2.__version__,
            "blosc2_codec": "ZSTD",
            "blosc2_clevel": 5,
            "blosc2_filter": "BITSHUFFLE",
            "blosc2_threads": 1,
            "chunk_variants": 128,
        },
        "jit_first_small_call_s": jit,
        "rows": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="docs/results/explore-genotypes.json")
    parser.add_argument("--variants", type=int, default=8192)
    parser.add_argument("--samples", type=int, default=1024)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.variants < 64 or args.variants * args.samples * 2 > 32 * 2**20:
        parser.error("Require >=64 variants and <=32MiB dense allele payload")
    result = run(args.variants, args.samples, args.repeats)
    with open(args.output, "w") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
