"""Bounded constructor-only exact memoization; benchmark prototype, not API.

Pins Python storage to65c7a89 with current native helpers. The cache admits
complete rawbytes keys and immutable finalrecords, stops admission when full,
and is always cleared when construction exits. Admission stages a temporary
dictcopy: this scratch is outside the retained-cache budget and counted by RSS.
No eviction policy or digest-only equality is used. Coldrecords may share bytes.
"""

import argparse
import hashlib
import json
import random
import resource
import statistics
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import numpy as np

from benchmarks import compressed_rle_policy as loader
from benchmarks.compressed_storage import dataset, source_hashes
from tightarray import _core

BASELINE = "65c7a89"
BUDGETS = (65536, 262144, 1048576)
NAMES = (
    "identical",
    "period31",
    "period67",
    "unique32",
    "incompressible",
    "rare",
    "uniform",
)
MISSING = object()


class Memo:
    __slots__ = (
        "admissions",
        "budget",
        "closed",
        "entries",
        "entry_bytes",
        "hits",
        "misses",
        "peak",
    )

    def __init__(self, budget):
        self.entries = {}
        self.entry_bytes = 0
        self.budget = budget
        self.closed = False
        self.hits = self.misses = self.peak = self.admissions = 0
        if self.owned(self.entries) > budget:
            raise ValueError("budget smaller than empty cache metadata")
        self.peak = self.owned(self.entries)

    def owned(self, entries, entry_bytes=None):
        # Conservative: shared integers/bytes counted repeatedly rather than deduped.
        return (
            sys.getsizeof(self)
            + sys.getsizeof(entries)
            + sum(
                sys.getsizeof(getattr(self, name))
                for name in self.__slots__
                if name != "entries"
            )
            + (self.entry_bytes if entry_bytes is None else entry_bytes)
        )

    def lookup(self, key):
        value = self.entries.get(key, MISSING)
        if value is MISSING:
            self.misses += 1
        else:
            self.hits += 1
        self.peak = max(self.peak, self.owned(self.entries))
        assert self.peak <= self.budget
        return value

    def admit(self, key, value):
        if self.closed:
            return
        staged = self.entries.copy()
        staged[key] = value
        extra = sys.getsizeof(key) + sys.getsizeof(value)
        retained = self.owned(staged, self.entry_bytes + extra)
        if retained <= self.budget:
            self.entries = staged
            self.entry_bytes += extra
            self.admissions += 1
            self.peak = max(self.peak, self.owned(self.entries))
        else:
            self.closed = True
        assert self.owned(self.entries) <= self.budget

    def finish(self):
        result = {
            "budget_bytes": self.budget,
            "hits": self.hits,
            "misses": self.misses,
            "admissions": self.admissions,
            "peak_retained_bytes": self.peak,
            "entries": len(self.entries),
            "closed": self.closed,
        }
        self.entries.clear()
        self.entry_bytes = 0
        return result


def memo_class(base, budget):
    class Memoized(base):
        last_memo = None

        def __init__(self, *args, **kwargs):
            cache = Memo(budget)
            self._constructor_memo = cache
            try:
                super().__init__(*args, **kwargs)
            finally:
                type(self).last_memo = cache.finish()
                del self._constructor_memo

        def _encode(self, raw):
            cache = getattr(self, "_constructor_memo", None)
            if cache is None:
                return super()._encode(raw)
            found = cache.lookup(raw)
            if found is not MISSING:
                return found
            result = super()._encode(raw)
            cache.admit(raw, result)
            return result

    return Memoized


@contextmanager
def pinned():
    with (
        patch.object(loader, "BASELINE_COMMIT", BASELINE),
        loader.pinned_baseline() as result,
    ):
        yield result


def data_for(name, size):
    rng = np.random.default_rng(175)
    if name == "identical":
        return np.tile(rng.integers(32, size=4096, dtype=np.uint8), size // 4096)
    if name in ("period31", "period67"):
        period = int(name.removeprefix("period"))
        return np.resize(rng.integers(32, size=period, dtype=np.uint8), size)
    if name == "unique32":
        return rng.integers(32, size=size, dtype=np.uint8)
    if name == "incompressible":
        return rng.integers(256, size=size, dtype=np.uint8)
    if name == "rare":
        return dataset("rare-spikes", size, 4096)
    if name == "uniform":
        return dataset("uniform-chunks", size, 4096)
    raise ValueError(name)


def guards():
    result = source_hashes()
    result["benchmark"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result["loaded_extension"] = hashlib.sha256(
        Path(_core.__file__).read_bytes()
    ).hexdigest()
    return result


def peak_rss():
    n = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return n if sys.platform == "darwin" else n * 1024


def construct(cls, data, codec):
    start = time.perf_counter()
    arr = cls(data, chunk_size=4096, cache_bytes=65536, codec=codec)
    elapsed = (time.perf_counter() - start) * 1000
    info = arr.storage_info()
    return arr, {
        "build_ms": elapsed,
        "cold_stored_bytes": info.stored_bytes,
        "cold_owned_bytes": info.owned_bytes,
        "memo": getattr(cls, "last_memo", None),
    }


def run(size=1 << 20, repeats=5):
    if size < 4096 or size % 4096 or repeats < 1:
        raise ValueError("size must be a positive multiple of4096; repeats>=1")
    before = guards()
    rows = []
    rng = random.Random(917)
    with pinned() as (base, source):
        classes = {
            "baseline": base,
            **{f"memo-{b}": memo_class(base, b) for b in BUDGETS},
        }
        for name in NAMES:
            data = data_for(name, size)
            for codec in ("none", "zstd"):
                samples = {key: [] for key in classes}
                baseline = base(data, chunk_size=4096, cache_bytes=65536, codec=codec)
                records = baseline._chunks.copy()
                del baseline
                for _ in range(repeats):
                    order = list(classes)
                    rng.shuffle(order)
                    for key in order:
                        arr, result = construct(classes[key], data, codec)
                        assert arr._chunks == records
                        assert arr.tobytes() == data.tobytes()
                        # Verify sharing cannot couple later modifications in different chunks.
                        old = int(data[0])
                        arr[0] = (old + 1) % 256
                        arr.flush()
                        arr.clear_cache()
                        expected = data.copy()
                        expected[0] = (old + 1) % 256
                        assert arr.tobytes() == expected.tobytes()
                        samples[key].append(result)
                        del arr
                rows.append({"case": name, "codec": codec, "samples": samples})
                print(
                    name,
                    codec,
                    {
                        key: round(statistics.median(x["build_ms"] for x in vals), 3)
                        for key, vals in samples.items()
                    },
                    flush=True,
                )
    if guards() != before:
        raise RuntimeError("source changed during timing")
    return {
        "baseline_commit": BASELINE,
        "baseline_python_sha256": hashlib.sha256(source).hexdigest(),
        "source_sha256": before,
        "size": size,
        "repeats": repeats,
        "seed": 917,
        "rows": rows,
        "memory": "Cache budget conservatively counts retained helper/dict/keys/records; staging copy and encoding scratch excluded. Cold owned is retained graph estimate, not RSS.",
        "scope": "Whole construction, not app E2E; memo removed before timed constructor returns. Cold records immutable and sharing validated through edits.",
    }


def memory_worker(name, codec, budget, size):
    # Each invocation is a fresh process; input, imports and library initialization
    # precede the peakbaseline. Delta is incremental high-water RSS, not current RSS.
    data = data_for(name, size)
    with pinned() as (base, _):
        cls = base if budget == 0 else memo_class(base, budget)
        cls(b"", codec=codec)
        before = peak_rss()
        arr, result = construct(cls, data, codec)
        after = peak_rss()
        result.update(
            case=name,
            codec=codec,
            budget=budget,
            peak_before=before,
            peak_after=after,
            incremental_peak_bytes=max(0, after - before),
        )
        assert len(arr) == size
    return result


def memory_runs(size):
    before = guards()
    rows = []
    for name in ("identical", "unique32"):
        for codec in ("none", "zstd"):
            for budget in (0, 65536, 1048576):
                output = subprocess.check_output(
                    [
                        sys.executable,
                        "-m",
                        "benchmarks.compressed_constructor_memo",
                        "--worker",
                        name,
                        "--codec",
                        codec,
                        "--budget",
                        str(budget),
                        "--size",
                        str(size),
                    ],
                    text=True,
                )
                rows.append(json.loads(output))
    if guards() != before:
        raise RuntimeError("source changed during RSS workers")
    return {
        "source_sha256": before,
        "size": size,
        "rows": rows,
        "scope": "Fresh-process peak RSS and incremental high-water growth; baseline before array construction includes source and imports. Not a bound on live codec scratch.",
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path)
    p.add_argument("--size", type=int, default=1 << 20)
    p.add_argument("--repeats", type=int, default=5)
    p.add_argument("--memory", action="store_true")
    p.add_argument("--worker", choices=NAMES)
    p.add_argument("--codec", choices=("none", "zstd"), default="none")
    p.add_argument("--budget", type=int, default=0)
    args = p.parse_args()
    if args.worker:
        print(
            json.dumps(memory_worker(args.worker, args.codec, args.budget, args.size))
        )
    else:
        if args.output is None:
            p.error("--output required")
        result = memory_runs(args.size) if args.memory else run(args.size, args.repeats)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
