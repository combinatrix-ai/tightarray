"""Compare codec-free SIMD writes against cached dense Blosc2 writes."""

import json
import statistics
import time
from pathlib import Path

from benchmarks.compressed_hot_bulk import cases, make_trace, source_guards
from benchmarks.compressed_span_bulk import dense_write
from benchmarks.compressed_storage import Store


def run():
    before = source_guards()
    records = []
    methods = ["palette-none", "dense-lz4", "dense-zstd"]
    for name, (data, labels) in cases().items():
        if name.endswith("control"):
            continue
        for width in (64, 256, 1024):
            writes, expected, _ = make_trace(data, labels, width, count=32)
            samples = {method: [] for method in methods}
            for repeat in range(9):
                order = methods[repeat % 3 :] + methods[: repeat % 3]
                for method in order:
                    store = Store(data, method, 4096, 65536)
                    store.read(0, 1)
                    begin = time.perf_counter_ns()
                    for start, value in writes:
                        if method == "palette-none":
                            store.data.write(start, value)
                        else:
                            dense_write(store.data, start, value)
                    updated = time.perf_counter_ns()
                    store.flush()
                    flushed = time.perf_counter_ns()
                    assert store.read(0, len(data)) == expected
                    hot = store.info()
                    store.clear()
                    cold = store.info()
                    assert store.read(0, len(data)) == expected
                    samples[method].append(
                        {
                            "updates_us": (updated - begin) / 1000,
                            "total_us": (flushed - begin) / 1000,
                            "hot": hot,
                            "cold": cold,
                        }
                    )
            records.append(
                {
                    "case": name,
                    "width": width,
                    "samples": samples,
                    "median_us": {
                        method: {
                            key: statistics.median(s[key] for s in values)
                            for key in ("updates_us", "total_us")
                        }
                        for method, values in samples.items()
                    },
                }
            )
    assert before == source_guards()
    return {
        "source_sha256": before,
        "repeats": 9,
        "writes": 32,
        "chunk_bytes": 4096,
        "cache_bytes": 65536,
        "scope": "Rotated within-process warm trials; changed scattered contiguous writes; construction excluded; dense custom uint8 LRU, clevel5 BITSHUFFLE typesize1 nthreads1; retained graph is not RSS.",
        "records": records,
    }


if __name__ == "__main__":
    Path("docs/compressed-simd-blosc-results.json").write_text(
        json.dumps(run(), indent=2) + "\n"
    )
