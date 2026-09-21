"""Split public bulk-write update/flush time and count codec work separately."""

import argparse
import hashlib
import json
import random
import time
from dataclasses import asdict
from pathlib import Path

import tightarray.compressed as live
from benchmarks.compressed_hot_bulk import cases, cold_hash, make_trace
from benchmarks.compressed_span_bulk import dense_write
from benchmarks.compressed_storage import DenseLRU
from benchmarks.compressed_trimmed_policy import guards, retained_graph_bytes


def source_guards():
    result = guards()
    root = Path(__file__).resolve().parents[1]
    for path in [
        Path(__file__),
        root / "benchmarks/compressed_hot_bulk.py",
        root / "benchmarks/compressed_span_bulk.py",
        root / "benchmarks/compressed_span_bulk_native.py",
        *(root / "tightarray").glob("_compressed*.h"),
    ]:
        result[str(path.relative_to(root))] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    return result


def make_store(data, budget, codec, dense):
    if dense:
        return DenseLRU(data, 4096, budget, codec)
    return live.CompressedArray(data, chunk_size=4096, cache_bytes=budget, codec=codec)


def info(array, dense, budget):
    result = array.info() if dense else asdict(array.storage_info())
    result["owned_bytes"] = retained_graph_bytes(array)
    assert result["cache_bytes"] <= budget
    return result


def write_all(array, writes, dense):
    for start, values in writes:
        if dense:
            dense_write(array, start, values)
        else:
            array.write(start, values)


def trial(data, budget, codec, dense, writes, expected):
    array = make_store(data, budget, codec, dense)
    assert array[2048] == int(data[2048])
    before = info(array, dense, budget)
    begin = time.perf_counter()
    write_all(array, writes, dense)
    updated = time.perf_counter()
    array.flush()
    flushed = time.perf_counter()
    after = info(array, dense, budget)
    cold = None if dense else cold_hash(array)
    assert array.read(0, len(data)) == expected
    array.clear_cache()
    assert array.read(0, len(data)) == expected
    return {
        "updates_ms": (updated - begin) * 1000,
        "flush_ms": (flushed - updated) * 1000,
        "total_ms": (flushed - begin) * 1000,
        "before": before,
        "after": after,
        "reloaded": info(array, dense, budget),
        "cold_sha256": cold,
    }


def instrument(data, budget, codec, dense, writes, expected):
    stats = {
        "encode_calls": 0,
        "encode_input_bytes": 0,
        "compress_calls": 0,
        "compress_input_bytes": 0,
        "bitshuffle_calls": 0,
        "no_filter_calls": 0,
    }

    class CountedAdaptive(live.CompressedArray):
        def _encode(self, raw):
            stats["encode_calls"] += 1
            stats["encode_input_bytes"] += len(raw)
            return super()._encode(raw)

        def _compress(self, raw, *, shuffle):
            stats["compress_calls"] += 1
            stats["compress_input_bytes"] += len(raw)
            stats["bitshuffle_calls" if shuffle else "no_filter_calls"] += 1
            return super()._compress(raw, shuffle=shuffle)

    class CountedDense(DenseLRU):
        def encode(self, raw):
            stats["encode_calls"] += 1
            stats["encode_input_bytes"] += len(raw)
            stats["compress_calls"] += 1
            stats["compress_input_bytes"] += len(raw)
            stats["bitshuffle_calls"] += 1
            return super().encode(raw)

    array = (
        CountedDense(data, 4096, budget, codec)
        if dense
        else CountedAdaptive(data, chunk_size=4096, cache_bytes=budget, codec=codec)
    )
    assert array[2048] == int(data[2048])
    stats.update(dict.fromkeys(stats, 0))
    write_all(array, writes, dense)
    updates = stats.copy()
    array.flush()
    flush = {k: stats[k] - updates[k] for k in stats}
    assert array.read(0, len(data)) == expected
    array.clear_cache()
    assert array.read(0, len(data)) == expected
    return {
        "updates": updates,
        "flush": flush,
        "total": {k: updates[k] + flush[k] for k in stats},
    }


def run(repeats=31):
    before = source_guards()
    rng = random.Random(742)
    records = []
    for name, (data, labels) in cases().items():
        for budget in (512, 65536):
            for width in (16, 256):
                # Span control uses the interior so its compact hot path is
                # measured; other cases sample partial positions throughout.
                if name == "span-control":
                    from benchmarks.compressed_span_bulk_native import sized_trace

                    writes, expected, changes = sized_trace(
                        data, labels, width, count=32
                    )
                else:
                    writes, expected, changes = make_trace(
                        data, labels, width, count=32
                    )
                for codec in ("none", "lz4", "zstd"):
                    methods = [False] if codec == "none" else [False, True]
                    samples = {("dense" if d else "adaptive"): [] for d in methods}
                    for _ in range(repeats):
                        rng.shuffle(methods)
                        for dense in methods:
                            samples["dense" if dense else "adaptive"].append(
                                trial(data, budget, codec, dense, writes, expected)
                            )
                    counts = {
                        ("dense" if d else "adaptive"): instrument(
                            data, budget, codec, d, writes, expected
                        )
                        for d in methods
                    }
                    records.append(
                        {
                            "case": name,
                            "cache_bytes": budget,
                            "write_bytes": width,
                            "write_count": 32,
                            "changed_values": changes,
                            "codec": codec,
                            "samples": samples,
                            "untimed_counts": counts,
                        }
                    )
                print(name, budget, width, "complete", flush=True)
    assert before == source_guards(), "Measured sources changed during benchmark"
    return {
        "source_sha256": before,
        "repeats": repeats,
        "records": records,
        "scope": "Current99377a7-era public operations versus matching dense codecs.31balanced independentlyconstructed/prewarmed trials perconfig;32actualchanged partial writes. Updates,flush,total separatelytimed with contiguous perf_counter boundaries. Construction excluded. Separate instrumentedpass counts encode calls and candidate compression bytes/filter. Exactvalues/flushreload/cachebounds checked. Dense helper receivesprevalidatedbytes/lacksfullAPIvalidation, samepayloadbudget notRSS.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=31)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("repeats mustbe positive")
    Path(args.output).write_text(json.dumps(run(args.repeats), indent=2) + "\n")
