"""Disposable context-reuse study promoted to a portable benchmark.

Historical JSON came from the earlier /tmp version, not this refactor. Timings
compare all exhaustive candidates, no selection heuristic. Contexts keyed by
filter AND payload length preserve measured compressed bytes; a filter-only
pool is a negative control. SChunk retains opaque C workspaces not represented
by .cbytes or Python shallow size. Use --memory for fresh-process RSS estimates.
"""

import argparse
import gc
import hashlib
import json
import os
import platform
import random
import resource
import statistics
import subprocess
import sys
import time
from pathlib import Path

import blosc2

from benchmarks.compressed_codec_policy import candidates, extras
from benchmarks.compressed_storage import CASES, dataset


def params(codec, shuffle):
    return {
        "codec": blosc2.Codec.LZ4 if codec == "lz4" else blosc2.Codec.ZSTD,
        "clevel": 5,
        "typesize": 1,
        "nthreads": 1,
        "filters": [blosc2.Filter.BITSHUFFLE if shuffle else blosc2.Filter.NOFILTER],
    }


class Reuse:
    def __init__(self, codec, by_length=True):
        self.codec = codec
        self.by_length = by_length
        self.pool = {}
        self.setup_s = 0

    def encode(self, raw, shuffle):
        key = (shuffle, len(raw)) if self.by_length else shuffle
        if key not in self.pool:
            tick = time.perf_counter()
            self.pool[key] = blosc2.SChunk(
                chunksize=len(raw),
                data=raw,
                cparams=params(self.codec, shuffle),
                dparams={"nthreads": 1},
                contiguous=False,
            )
            self.setup_s += time.perf_counter() - tick
        else:
            self.pool[key].update_data(0, raw, copy=False)
        return self.pool[key].get_chunk(0)

    def info(self):
        return {
            "contexts": len(self.pool),
            "retained_compressed_bytes": sum(x.cbytes for x in self.pool.values()),
            "retained_logical_bytes": sum(x.nbytes for x in self.pool.values()),
            "python_shallow_bytes": sum(sys.getsizeof(x) for x in self.pool.values()),
            "setup_s": self.setup_s,
        }


def run(size=2**18, chunk=4096, repeats=7):
    cases = [(name, dataset(name, size, chunk)) for name in CASES] + list(
        extras(size, chunk, True)
    )
    tasks = []
    for name, data in cases:
        # Distinct independent payloads including their varying packed widths.
        for start in range(0, size, chunk):
            raw = data[start : start + chunk].tobytes()
            items, _ = candidates(raw)
            if isinstance(items, int):
                continue
            for item in items:
                if len(item.payload) >= 64:
                    tasks.append(
                        (
                            name,
                            item.mode,
                            bool(item.palette),
                            item.payload,
                            item.mode == "bytes",
                            len(item.palette),
                        )
                    )
    rng = random.Random(9182)
    rng.shuffle(tasks)
    rows = []
    checks = []
    for codec in ["lz4", "zstd"]:
        reuse = Reuse(codec)
        varying = Reuse(codec, False)
        same_bytes = True
        varying_same = True
        variable_failures = []
        old_samples = []
        new_samples = []
        # Exact result comparison, independent decode and retained bytes immutability.
        held = None
        reference_sizes = []
        reuse_sizes = []
        for i, (_, _, _, raw, shuffle, pal) in enumerate(tasks):
            base = blosc2.compress2(raw, **params(codec, shuffle))
            value = reuse.encode(raw, shuffle)
            other = varying.encode(raw, shuffle)
            same_bytes &= value == base
            varying_same &= other == base
            assert len(value) == len(base) and value == base
            assert blosc2.decompress2(value, nthreads=1) == raw
            if other != base:
                variable_failures.append(
                    {
                        "length": len(raw),
                        "shuffle": shuffle,
                        "base_bytes": len(base),
                        "reuse_bytes": len(other),
                    }
                )
            assert blosc2.decompress2(other, nthreads=1) == raw
            reference_sizes.append(len(base) + pal)
            reuse_sizes.append(len(value) + pal)
            if held is None:
                held = (value, hashlib.sha256(value).digest())
            assert hashlib.sha256(held[0]).digest() == held[1]
        # Exercise last-partial sizes changing within a single slot. Independent chunks.
        partial = []
        for length in [17, 63, 64, 65, 513, 4095, 4096, 127, 8192, 33]:
            raw = bytes((i * 31) % 251 for i in range(length))
            for shuffle in [False, True]:
                base = blosc2.compress2(raw, **params(codec, shuffle))
                out = varying.encode(raw, shuffle)
                partial.append({"length": length, "shuffle": shuffle, "exact": out == base})
                assert blosc2.decompress2(out, nthreads=1) == raw
        checks.append(
            {
                "codec": codec,
                "exact_bytes": same_bytes,
                "variable_length_exact": varying_same,
                "variable_failure_count": len(variable_failures),
                "variable_failures_sample": variable_failures[:10],
                "partial": partial,
                "pool_by_length": reuse.info(),
                "pool_variable_length": varying.info(),
            }
        )
        # Prewarmed contexts; randomized paired backend order, all samples retained.
        for _ in range(repeats):
            order = ["compress2", "reuse"]
            rng.shuffle(order)
            for method in order:
                tick = time.perf_counter()
                if method == "compress2":
                    for _, _, _, raw, shuffle, _ in tasks:
                        blosc2.compress2(raw, **params(codec, shuffle))
                else:
                    for _, _, _, raw, shuffle, _ in tasks:
                        reuse.encode(raw, shuffle)
                elapsed = time.perf_counter() - tick
                (old_samples if method == "compress2" else new_samples).append(elapsed)
        rows.append(
            {
                "codec": codec,
                "tasks": len(tasks),
                "compress2_s": statistics.median(old_samples),
                "reuse_s": statistics.median(new_samples),
                "speedup": statistics.median(old_samples) / statistics.median(new_samples),
                "compress2_samples": old_samples,
                "reuse_samples": new_samples,
                "reuse_info": reuse.info(),
            }
        )
        print(rows[-1], flush=True)
    result = {
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "blosc2": blosc2.__version__,
        },
        "case_count": len(cases),
        "dataset_size": size,
        "chunk": chunk,
        "seed": 9182,
        "checks": checks,
        "rows": rows,
        "peak_rss_process": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "note": "RSS is whole experiment high-watermark, NOT per-context memory. cbytes excludes opaque C context/workspace. Length-keyed pools preserve all compared candidate bytes and exhaustive size choices; filter-only pools are a negative control and can change them. Setup measured separately, warm timings include update_data+get_chunk copies.",
    }
    return result


def current_rss():
    # ps RSS is KiB on the supported Unix/macOS benchmark hosts.
    return (
        int(
            subprocess.check_output(
                ["ps", "-o", "rss=", "-p", str(os.getpid())], text=True
            ).strip()
        )
        * 1024
    )


def memory_worker(codec, requested, budget_mib):
    # Eight packed widths for 4096 values, plus shuffled uint8 = nine contexts.
    rng = random.Random(1931)
    samples = [
        (bytes(rng.randrange(256) for _ in range(length)), False)
        for length in range(512, 4097, 512)
    ]
    samples.append((bytes(rng.randrange(256) for _ in range(4096)), True))
    gc.collect()
    before = current_rss()
    pools = []
    for _ in range(requested):
        pool = Reuse(codec)
        for raw, shuffle in samples:
            pool.encode(raw, shuffle)
        pools.append(pool)
        del pool
        if current_rss() > budget_mib * 2**20:
            break
    after = current_rss()
    info = [pool.info() for pool in pools]
    result = {
        "codec": codec,
        "requested_pools": requested,
        "created_pools": len(pools),
        "contexts": sum(row["contexts"] for row in info),
        "rss_before": before,
        "rss_after": after,
        "rss_delta": after - before,
        "retained_compressed_bytes": sum(
            row["retained_compressed_bytes"] for row in info
        ),
        "budget_mib": budget_mib,
        "completed": len(pools) == requested,
    }
    pools.clear()
    gc.collect()
    result["rss_after_clear"] = current_rss()
    result["allocator_retained_delta"] = result["rss_after_clear"] - before
    return result


def memory_study(budget_mib):
    rows = []
    for codec in ("lz4", "zstd"):
        for count in (0, 1, 10, 100, 500):
            command = [
                sys.executable,
                "-m",
                "benchmarks.compressed_codec_context",
                "--memory-worker",
                codec,
                str(count),
                "--budget-mib",
                str(budget_mib),
            ]
            row = json.loads(subprocess.check_output(command, text=True))
            rows.append(row)
            print(row, flush=True)
            if not row["completed"]:
                break
    return {
        "rows": rows,
        "note": "Fresh process for each count. RSS delta includes native contexts, compressed chunks, Python bookkeeping, allocator effects and ps sampling; not an exact C allocation count. Clear/free may leave allocator pages resident.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output")
    parser.add_argument("--size", type=int, default=2**18)
    parser.add_argument("--chunk", type=int, default=4096)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--memory", action="store_true")
    parser.add_argument("--memory-worker", nargs=2)
    parser.add_argument("--budget-mib", type=int, default=256)
    args = parser.parse_args()
    if args.memory_worker:
        print(
            json.dumps(
                memory_worker(
                    args.memory_worker[0], int(args.memory_worker[1]), args.budget_mib
                )
            )
        )
        return
    if not args.output:
        parser.error("--output is required")
    if args.size <= 0 or args.chunk < 64 or args.size % args.chunk or args.repeats < 1:
        parser.error("Require positive size divisible by chunk>=64 and repeats>=1")
    result = (
        memory_study(args.budget_mib)
        if args.memory
        else run(args.size, args.chunk, args.repeats)
    )
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
