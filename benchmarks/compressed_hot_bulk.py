"""Paired ordinary cached bulk writes, capacity tradeoffs and eviction control."""

import argparse
import hashlib
import json
import random
import time
from pathlib import Path

import numpy as np

import benchmarks.compressed_storage as harness
import tightarray.compressed as live
from benchmarks.compressed_span_bulk import dense_write
from benchmarks.compressed_trimmed_policy import (
    guards,
    pinned_baseline,
    retained_graph_bytes,
)

BASELINE = "ae5c4ff"


def source_guards():
    result = guards()
    root = Path(__file__).resolve().parents[1]
    for path in [
        Path(__file__),
        root / "benchmarks/compressed_span_bulk.py",
        *(root / "tightarray").glob("_compressed*.h"),
    ]:
        result[str(path.relative_to(root))] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    return result


def cases():
    rng = np.random.default_rng(734)
    result = {}
    for bits, palette in ((3, False), (5, False), (8, False), (3, True), (5, True)):
        labels = np.arange(
            256 - 2**bits if palette else 0, 256 if palette else 2**bits, dtype=np.uint8
        )
        values = rng.choice(labels, size=4096)
        result[f"{'palette' if palette else 'direct'}-{bits}bit"] = values, labels
    labels = np.arange(32, dtype=np.uint8)
    result["periodic-control"] = np.tile(labels, 128), labels
    span = np.zeros(4096, dtype=np.uint8)
    span[1792:2304] = rng.integers(32, size=512, dtype=np.uint8)
    result["span-control"] = span, labels
    return result


def make_trace(data, labels, width, count=16):
    rng = np.random.default_rng(735 + width)
    expected = bytearray(data.tobytes())
    alphabet = [int(x) for x in labels]
    table = bytes(
        {v: alphabet[(i + 1) % len(alphabet)] for i, v in enumerate(alphabet)}.get(
            i, int(labels[0])
        )
        for i in range(256)
    )
    writes = []
    for start in rng.integers(0, len(data) - width + 1, size=count):
        start = int(start)
        old = bytes(expected[start : start + width])
        new = old.translate(table)
        assert all(a != b for a, b in zip(old, new, strict=True))
        expected[start : start + width] = new
        writes.append((start, new))
    return writes, bytes(expected), count * width


def cold_hash(array):
    digest = hashlib.sha256()
    for chunk in array._chunks:
        if isinstance(chunk, int):
            digest.update(b"I" + bytes([chunk]))
        else:
            digest.update(b"B" + len(chunk).to_bytes(8, "little") + chunk)
    return digest.hexdigest()


def trial(cls, backend, data, budget, writes, expected):
    original = live.CompressedArray
    try:
        live.CompressedArray = cls
        store = harness.Store(data, backend, 4096, budget)
    finally:
        live.CompressedArray = original
    assert store.data[0] == int(data[0])

    def info():
        value = store.info()
        value["owned_bytes"] = retained_graph_bytes(store.data)
        assert value["cache_bytes"] <= budget
        return value

    before = info()
    begin = time.perf_counter()
    for start, values in writes:
        if backend.startswith("dense-"):
            dense_write(store.data, start, values)
        else:
            store.data.write(start, values)
    store.flush()
    elapsed = (time.perf_counter() - begin) * 1000
    after = info()
    cold = None if backend.startswith("dense-") else cold_hash(store.data)
    assert store.read(0, len(data)) == expected
    store.clear()
    assert store.read(0, len(data)) == expected
    return {
        "writes_flush_ms": elapsed,
        "before": before,
        "after": after,
        "reloaded": info(),
        "cold_sha256": cold,
    }


def configurations():
    for name, (data, labels) in cases().items():
        for budget in (0, 512, 65536):
            for width in (1, 16, 64, 256, 4096) if budget == 65536 else (16, 256, 4096):
                writes, expected, changes = make_trace(data, labels, width)
                yield name, data, budget, width, writes, expected, changes
    # Removing the only third label allows a repack from two to one bit. A fast
    # in-place write may retain the wider hot palette even when cold shrinks.
    rng = np.random.default_rng(736)
    shrink = rng.integers(2, size=4096, dtype=np.uint8)
    shrink[2048] = 7
    expected = bytearray(shrink.tobytes())
    expected[2048] = 0
    for budget in (0, 512, 65536):
        yield "remove-only-max", shrink, budget, 1, [(2048, b"\0")], bytes(expected), 1
    # Four chunks cycle through a budget holding only one 3-bit hot chunk.
    data = rng.integers(8, size=16384, dtype=np.uint8)
    expected = bytearray(data.tobytes())
    writes = []
    for i in range(32):
        start = (i % 4) * 4096 + (i * 17) % 4000
        value = bytes((v + 1) % 8 for v in expected[start : start + 16])
        writes.append((start, value))
        expected[start : start + 16] = value
    yield "eviction-direct3", data, 2048, 16, writes, bytes(expected), 512


def run(repeats=5):
    before = source_guards()
    original = live.CompressedArray
    rng, records = random.Random(737), []
    with pinned_baseline(BASELINE) as (base, source):
        for case, data, budget, width, writes, expected, changes in configurations():
            for codec in ("none", "zstd"):
                methods = [
                    ("base", base, f"palette-{codec}"),
                    ("live", original, f"palette-{codec}"),
                ]
                if codec == "zstd":
                    methods.append(("dense-zstd", original, "dense-zstd"))
                samples = {name: [] for name, _, _ in methods}
                for _ in range(repeats):
                    rng.shuffle(methods)
                    for name, cls, backend in methods:
                        samples[name].append(
                            trial(cls, backend, data, budget, writes, expected)
                        )
                assert all(
                    a["cold_sha256"] == b["cold_sha256"]
                    for a, b in zip(samples["base"], samples["live"], strict=True)
                ), (case, budget, width, codec)
                records.append(
                    {
                        "case": case,
                        "logical_bytes": len(data),
                        "cache_bytes": budget,
                        "write_bytes": width,
                        "write_count": len(writes),
                        "changed_values": changes,
                        "codec": codec,
                        "samples": samples,
                    }
                )
            print(case, budget, width, "complete", flush=True)
    assert before == source_guards(), "Measured sources changed during benchmark"
    return {
        "baseline_commit": BASELINE,
        "baseline_python_sha256": hashlib.sha256(source).hexdigest(),
        "source_sha256": before,
        "repeats": repeats,
        "records": records,
        "seeds": {"data": 734, "trace": 735, "special": 736, "order": 737},
        "scope": "Pinned Python/current native baseline versus live ordinary Hot bulk path. Changed values verified; writes+flush timed, construction excluded. All logical/cache checks and afterflush adaptive cold-record SHA equality checked. Hot width may intentionally remain wider after changes; before/after/reloaded retained graph reported, not RSS. Dense chunk-slice helper uses prevalidated bytes and lacks full API validation; same payload budget not same process memory.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("repeats must be positive")
    Path(args.output).write_text(json.dumps(run(args.repeats), indent=2) + "\n")
