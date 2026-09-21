"""Constructor memo policy comparison, benchmark-only; no production edits.

Pinned d90c7dd source is injected exactly once AFTER uniform detection and
BEFORE direct_bits. The hook reuses the existing alphabet scan; hits therefore
still scan raw bytes. Codec none bypasses memo completely. Historical prototype
and results are unchanged. Shared encoded bytes are immutable.
"""

import argparse
import hashlib
import json
import random
import statistics
import subprocess
import sys
import types
from contextlib import contextmanager
from pathlib import Path

from benchmarks import compressed_constructor_memo as old

BASELINE = "d90c7dd"
BUDGETS = old.BUDGETS
NAMES = old.NAMES
MISSING = old.MISSING
data_for = old.data_for
construct = old.construct
peak_rss = old.peak_rss


class ReservedMemo:
    __slots__ = (
        "admissions",
        "budget",
        "closed",
        "entries",
        "hits",
        "misses",
        "payload",
        "peak",
        "reserved_peak",
    )

    def __init__(self, budget):
        if budget < 1024:
            raise ValueError("budget must cover 1024-byte metadata reservation")
        self.entries = {}
        self.payload = 0
        self.budget = budget
        self.hits = self.misses = self.admissions = self.peak = 0
        self.reserved_peak = 1024
        self.closed = False
        self.peak = self.owned()

    def owned(self):
        return (
            sys.getsizeof(self)
            + sys.getsizeof(self.entries)
            + self.payload
            + sum(
                sys.getsizeof(getattr(self, k))
                for k in ReservedMemo.__slots__
                if k != "entries"
            )
        )

    def lookup(self, raw):
        result = self.entries.get(raw, MISSING)
        if result is MISSING:
            self.misses += 1
        else:
            self.hits += 1
        return result

    def admit(self, raw, result):
        if self.closed or raw in self.entries:
            return
        extra = sys.getsizeof(raw) + sys.getsizeof(result)
        reservation = 1024 + 256 * (len(self.entries) + 1) + self.payload + extra
        if reservation > self.budget:
            self.closed = True
            return
        self.entries[raw] = result
        self.payload += extra
        # Reservation is deliberately generous, but actual accounting is the
        # authority on other CPython builds. Only unexpected overshoot rebuilds.
        if self.owned() > reservation:
            del self.entries[raw]
            self.payload -= extra
            self.entries = self.entries.copy()
            self.closed = True
            if self.owned() > self.budget:
                self.entries.clear()
                self.payload = 0
            return
        self.admissions += 1
        self.peak = max(self.peak, self.owned())
        self.reserved_peak = max(self.reserved_peak, reservation)
        assert self.peak <= self.budget

    def finish(self):
        result = {
            "budget_bytes": self.budget,
            "hits": self.hits,
            "misses": self.misses,
            "admissions": self.admissions,
            "peak_retained_bytes": max(self.peak, self.owned()),
            "peak_reserved_bytes": self.reserved_peak,
            "entries": len(self.entries),
            "mapping_bytes": sys.getsizeof(self.entries),
            "closed": self.closed,
        }
        self.entries.clear()
        self.payload = 0
        return result


def lookup_after_uniform(self, raw):
    cache = getattr(self, "_constructor_memo", None)
    return MISSING if cache is None else cache.lookup(raw)


@contextmanager
def pinned():
    source = subprocess.check_output(
        ["git", "show", f"{BASELINE}:tightarray/compressed.py"],
        cwd=Path(__file__).resolve().parents[1],
    )
    marker = "        if len(colors) == 1:\n            return raw[0]\n"
    assert source.decode().count(marker) == 1
    modified = source.decode().replace(
        marker,
        marker
        + "        memo_result = _memo_lookup(self, raw)\n        if memo_result is not _memo_missing:\n            return memo_result\n",
    )
    modules = []
    try:
        classes = []
        for label, text in (("base", source), ("hook", modified)):
            name = f"tightarray._constructor_selective_{label}"
            module = types.ModuleType(name)
            module.__package__ = "tightarray"
            modules.append((name, sys.modules.get(name)))
            sys.modules[name] = module
            module.__dict__.update(
                _memo_lookup=lookup_after_uniform, _memo_missing=MISSING
            )
            exec(compile(text, name, "exec"), module.__dict__)  # noqa: S102
            classes.append(module.CompressedArray)
        yield *classes, source
    finally:
        for name, previous in modules:
            if previous is None:
                del sys.modules[name]
            else:
                sys.modules[name] = previous


def selective_class(base, budget, plain):
    class Selective(base):
        last_memo = None

        def __new__(cls, *args, **kwargs):
            if kwargs.get("codec", "none") == "none":
                cls.last_memo = None
                return plain(*args, **kwargs)
            return super().__new__(cls)

        def __init__(self, *args, **kwargs):
            if kwargs.get("codec", "none") == "none":
                super().__init__(*args, **kwargs)
                type(self).last_memo = None
                return
            cache = ReservedMemo(budget)
            self._constructor_memo = cache
            try:
                super().__init__(*args, **kwargs)
            finally:
                type(self).last_memo = cache.finish()
                del self._constructor_memo

        def _encode(self, raw):
            result = super()._encode(raw)
            cache = getattr(self, "_constructor_memo", None)
            if cache is not None and isinstance(result, bytes):
                cache.admit(raw, result)
            return result

    return Selective


def guards():
    result = old.guards()
    result["selective_benchmark"] = hashlib.sha256(
        Path(__file__).read_bytes()
    ).hexdigest()
    return result


def run(size=1 << 20, repeats=5):
    if size < 4096 or size % 4096 or repeats < 1:
        raise ValueError("size must be a positive multiple of4096; repeats>=1")
    before = guards()
    rows = []
    rng = random.Random(917)
    with pinned() as (base, hooked, source):
        classes = {
            "baseline": base,
            **{f"old-{b}": old.memo_class(base, b) for b in BUDGETS},
            **{f"selective-{b}": selective_class(hooked, b, base) for b in BUDGETS},
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
                        previous_value = int(data[0])
                        arr[0] = (previous_value + 1) % 256
                        arr.flush()
                        arr.clear_cache()
                        expected = data.copy()
                        expected[0] = (previous_value + 1) % 256
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
        "memory": "Selective cache reserves 1024 metadata bytes plus 256 per mapping entry plus exact key/record sizes; actual retained estimate checked on admission. Rollback/shrink scratch excluded. Old cache stages every admission. Cold owned is retained graph estimate, not RSS.",
        "scope": "Whole construction, not app E2E; memo removed before timed constructor returns. Cold records immutable and sharing validated through edits.",
    }


def memory_worker(name, codec, budget, size, policy):
    # Each invocation is a fresh process; input, imports and library initialization
    # precede the peakbaseline. Delta is incremental high-water RSS, not current RSS.
    data = data_for(name, size)
    with pinned() as (base, hooked, _):
        cls = (
            base
            if policy == "baseline"
            else (
                old.memo_class(base, budget)
                if policy == "old"
                else selective_class(hooked, budget, base)
            )
        )
        cls(b"", codec=codec)
        before = peak_rss()
        arr, result = construct(cls, data, codec)
        after = peak_rss()
        result.update(
            case=name,
            policy=policy,
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
            for policy, budget in (
                ("baseline", 0),
                ("old", 65536),
                ("old", 1048576),
                ("selective", 65536),
                ("selective", 1048576),
            ):
                output = subprocess.check_output(
                    [
                        sys.executable,
                        "-m",
                        "benchmarks.compressed_constructor_memo_selective",
                        "--policy",
                        policy,
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
    p.add_argument(
        "--policy", choices=("baseline", "old", "selective"), default="baseline"
    )
    p.add_argument("--budget", type=int, default=0)
    args = p.parse_args()
    if args.worker:
        print(
            json.dumps(
                memory_worker(
                    args.worker, args.codec, args.budget, args.size, args.policy
                )
            )
        )
    else:
        if args.output is None:
            p.error("--output required")
        result = memory_runs(args.size) if args.memory else run(args.size, args.repeats)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
