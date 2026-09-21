"""Benchmark exact endpoint candidates against native modal trimmed spans.

Only values equal to an endpoint can omit a nonempty prefix or suffix. Compare
both endpoints by exact packed/palette length, not by omitted run length. The
exhaustive baseline encoder is called once. Production code remains unchanged.
"""

import argparse
import hashlib
import json
import random
import statistics
from pathlib import Path

import numpy as np

import benchmarks.compressed_storage as harness
import tightarray.compressed as live
from benchmarks.compressed_trimmed_policy import (
    BASELINE_COMMIT,
    cases,
    guards,
    pinned_baseline,
    retained_graph_bytes,
    trimmed_class,
)


def candidate_size(raw, start, stop, palette=True):
    """Exact 8-byte-header plus native-word-rounded direct/palette payload."""
    colors = live._native._byte_palette(raw[start:stop])
    bits = max(1, colors[-1].bit_length())
    packed = ((stop - start) * bits + 63) // 64 * 8
    if palette and len(colors) < 256:
        width = max(1, (len(colors) - 1).bit_length())
        packed = min(packed, len(colors) + (((stop - start) * width + 63) // 64) * 8)
    return 8 + packed


def endpoint_class(base):
    parent = trimmed_class(base)

    class Endpoint(parent):
        def _encode(self, raw):
            original = base._encode(self, raw)
            if isinstance(original, int) or len(raw) > 65535:
                return original
            best_size = len(original)
            best = None
            for default, first, last in live._native._byte_edge_spans(raw):
                if first == 0 and last == len(raw):
                    continue
                # No allocation/scan of the interior if even one-bit packing
                # cannot beat the current best candidate.
                if 8 + ((last - first + 63) // 64) * 8 >= best_size:
                    continue
                size = candidate_size(raw, first, last, self._palette)
                if size < best_size:
                    best_size, best = size, (default, first, last)
            if best is None:
                return original
            default, first, last = best
            hot = self._make_hot(raw[first:last])
            words, offset = hot.data._word_view()
            assert offset == 0
            candidate = (
                bytes([0, len(hot.palette), default, hot.data.bits])
                + first.to_bytes(2, "little")
                + (last - first).to_bytes(2, "little")
                + hot.palette
                + words.tobytes()
            )
            assert len(candidate) == best_size
            return candidate

    return Endpoint


def extra_cases(size):
    yield from cases(size)
    rng = np.random.default_rng(725)
    chunks = size // 4096
    # Interior zero is modal, but nonmodal 31 at the left can be omitted.
    blocks = np.zeros((chunks, 4096), dtype=np.uint8)
    blocks[:, :1024] = 31
    blocks[:, 1024:1536] = rng.integers(1, 16, size=(chunks, 512), dtype=np.uint8)
    blocks[:, -1] = 1
    yield "nonmodal-long-edge", blocks.reshape(-1)
    # Shorter high-valued edge is the better omission: removing 255 permits
    # 2-bit direct storage, while removing the longer low edge retains 255.
    blocks = rng.integers(4, size=(chunks, 4096), dtype=np.uint8)
    blocks[:, :768] = 0
    blocks[:, 768] = 1
    blocks[:, -512:] = 255
    yield "distinct-edge-palette-adversary", blocks.reshape(-1)


def source_guards():
    result = guards()
    root = Path(__file__).resolve().parents[1]
    for path in (
        "tightarray/_compressed_trim.h",
        "benchmarks/compressed_trimmed_endpoints.py",
    ):
        result[path] = hashlib.sha256((root / path).read_bytes()).hexdigest()
    result["native_edges_source_note"] = (
        "_byte_edge_spans is compiled through recorded _core.c and _compressed_trim.h"
    )
    return result


def run(size=2**20, repeats=5):
    before = source_guards()
    rng = random.Random(724)
    original, original_info = live.CompressedArray, harness.Store.info
    records = []

    def graph_info(store):
        info = original_info(store)
        info["owned_bytes"] = retained_graph_bytes(store.data)
        return info

    try:
        harness.Store.info = graph_info
        with pinned_baseline() as (base, source):
            modal = trimmed_class(base, live._native._byte_trim)
            endpoint = endpoint_class(base)
            for name, data in extra_cases(size):
                operations = harness.traces(data, 4096)
                methods = [
                    (f"{label}-{codec}", cls, f"palette-{codec}")
                    for label, cls in (
                        ("base", base),
                        ("modal", modal),
                        ("endpoint", endpoint),
                    )
                    for codec in ("none", "zstd")
                ] + [
                    ("dense-lz4", base, "dense-lz4"),
                    ("dense-zstd", base, "dense-zstd"),
                ]
                samples = {label: [] for label, _, _ in methods}
                for _ in range(repeats):
                    rng.shuffle(methods)
                    for label, cls, backend in methods:
                        live.CompressedArray = cls
                        samples[label].append(
                            harness.trial(data, backend, 4096, 65536, operations)
                        )
                records.append({"case": name, "samples": samples})
                print(
                    name,
                    {
                        label: statistics.median(s["build_ms"] for s in rows)
                        for label, rows in samples.items()
                    },
                    flush=True,
                )
    finally:
        live.CompressedArray, harness.Store.info = original, original_info
    assert before == source_guards(), "Measured sources changed during benchmark"
    return {
        "baseline_commit": BASELINE_COMMIT,
        "baseline_python_sha256": hashlib.sha256(source).hexdigest(),
        "source_sha256": before,
        "size": size,
        "repeats": repeats,
        "seed": {"original": 723, "adversarial": 725, "order": 724, "traces": 914},
        "records": records,
        "scope": "Pinned Python baseline/current native extension. Endpoint selection compares exact uncompressed span candidates only. Cold retained graph includes custom fields; excludes runtime workspaces; not RSS. Python hot methods and exhaustive baseline encoding remain. All operation results checked.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=2**20)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.size < 4096 or args.size % 4096 or args.repeats < 1:
        parser.error("size must be a positive multiple of 4096; repeats >= 1")
    Path(args.output).write_text(
        json.dumps(run(args.size, args.repeats), indent=2) + "\n"
    )
