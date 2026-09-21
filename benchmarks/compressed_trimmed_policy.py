"""Benchmark-only modal trimmed-span representation; production stays unchanged.

Baseline Python implementation is pinned to eff5443 and uses the current native
extension. All measured source hashes are guarded across the run. A zero tag
marks an experimental 8-byte descriptor, palette, and packed interior. Cold
selection compares actual encoded lengths. Histogram and trimmed-hot methods
are Python/NumPy prototype costs, not claims about a future native backend.
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
from dataclasses import replace
from pathlib import Path

import numpy as np

import benchmarks.compressed_storage as storage_harness
import tightarray.compressed as live
from benchmarks.compressed_storage import dataset, source_hashes, traces, trial
from tightarray import Array

BASELINE_COMMIT = "eff5443"


class TrimmedHot:
    __slots__ = ("data", "default", "dirty", "length", "palette", "start")

    def __init__(self, data, palette, default, start, length):
        self.data, self.palette = data, palette
        self.default, self.start, self.length = default, start, length
        self.dirty = False

    @property
    def nbytes(self):
        return self.data.nbytes + len(self.palette)

    @property
    def repeated(self):
        # Existing write path expands structural entries before mutation.
        return True

    def __getitem__(self, index):
        if not self.start <= index < self.start + len(self.data):
            return self.default
        value = self.data[index - self.start]
        return self.palette[value] if self.palette else value

    def read(self, start=0, stop=None):
        if stop is None:
            stop = self.length
        out = bytearray([self.default]) * (stop - start)
        first = max(start, self.start)
        last = min(stop, self.start + len(self.data))
        if first < last:
            raw = self.data[first - self.start : last - self.start].tobytes()
            if self.palette:
                raw = raw.translate(self.palette.ljust(256, b"\0"))
            out[first - start : last - start] = raw
        return bytes(out)


def retained_graph_bytes(root):
    """Reachable owned Python/native-array graph, excluding shared codec modules."""
    seen = set()

    def visit(value):
        if isinstance(value, types.ModuleType) or id(value) in seen:
            return 0
        seen.add(id(value))
        total = sys.getsizeof(value)
        if isinstance(value, dict):
            total += sum(visit(key) + visit(item) for key, item in value.items())
        elif isinstance(value, (list, tuple, set)):
            total += sum(visit(item) for item in value)
        elif isinstance(value, TrimmedHot):
            total += sum(visit(getattr(value, key)) for key in TrimmedHot.__slots__)
        elif isinstance(value, live._native._Hot):
            total += visit(value.data) + visit(value.palette)
        elif hasattr(value, "__dict__") and not isinstance(value, type):
            # Codec enums and modules are shared runtime state, not array storage.
            if type(value).__module__ in ("blosc2", "enum"):
                return 0
            total += visit(value.__dict__)
        return total

    return visit(root)


def trimmed_class(base, recognizer=None):
    class Trimmed(base):
        def _encode(self, raw):
            original = super()._encode(raw)
            if isinstance(original, int) or len(raw) > 65535:
                return original
            if recognizer is None:
                default = int(
                    np.bincount(np.frombuffer(raw, dtype=np.uint8), minlength=256).argmax()
                )
                marker = bytes([default])
                first = len(raw) - len(raw.lstrip(marker))
                last = len(raw.rstrip(marker))
            else:
                default, first, last = recognizer(raw)
            if first == 0 and last == len(raw):
                return original
            # Even a one-bit span cannot beat this existing candidate.
            if 8 + ((last - first + 63) // 64) * 8 >= len(original):
                return original
            span = raw[first:last]
            colors = live._native._byte_palette(span)
            bits = max(1, colors[-1].bit_length())
            packed = ((len(span) * bits + 63) // 64) * 8
            if self._palette and len(colors) < 256:
                palette_bits = max(1, (len(colors) - 1).bit_length())
                packed = min(
                    packed, len(colors) + ((len(span) * palette_bits + 63) // 64) * 8
                )
            if 8 + packed >= len(original):
                return original
            hot = self._make_hot(span)
            words, offset = hot.data._word_view()
            assert offset == 0
            candidate = (
                bytes([0, len(hot.palette), default, hot.data.bits])
                + first.to_bytes(2, "little")
                + len(span).to_bytes(2, "little")
                + hot.palette
                + words.tobytes()
            )
            return candidate if len(candidate) < len(original) else original

        def _decode(self, chunk, length):
            if isinstance(chunk, bytes) and chunk[0] == 0:
                palette_length, default, bits = chunk[1:4]
                start = int.from_bytes(chunk[4:6], "little")
                span_length = int.from_bytes(chunk[6:8], "little")
                palette = chunk[8 : 8 + palette_length]
                data = Array._from_packed_bytes(
                    chunk, span_length, bits, 8 + palette_length
                )
                return TrimmedHot(data, palette, default, start, length)
            return super()._decode(chunk, length)

        def storage_info(self):
            return replace(
                super().storage_info(), owned_bytes=retained_graph_bytes(self)
            )

    return Trimmed


@contextmanager
def pinned_baseline():
    root = Path(__file__).resolve().parents[1]
    source = subprocess.check_output(
        ["git", "show", f"{BASELINE_COMMIT}:tightarray/compressed.py"], cwd=root
    )
    module = types.ModuleType("tightarray._trimmed_baseline")
    module.__package__ = "tightarray"
    sys.modules[module.__name__] = module
    try:
        exec(compile(source, "pinned_trimmed_baseline.py", "exec"), module.__dict__)  # noqa: S102
        yield module.CompressedArray, source
    finally:
        del sys.modules[module.__name__]


def cases(size):
    rng = np.random.default_rng(723)
    blocks = rng.integers(32, size=(size // 4096, 4096), dtype=np.uint8)
    half = blocks.copy()
    half[:, 2048:] = 0
    yield "half-random-half-zero", half.reshape(-1)
    yield "half-zero-half-random", half[:, ::-1].copy().reshape(-1)
    island = np.zeros_like(blocks)
    island[:, 1536:2560] = blocks[:, 1536:2560]
    yield "central-island", island.reshape(-1)
    yield "random32", blocks.reshape(-1)
    outliers = half.copy()
    outliers[:, -1] = 31
    yield "half-with-edge-outlier", outliers.reshape(-1)
    yield "rare-spikes", dataset("rare-spikes", size, 4096)
    yield "uniform-chunks", dataset("uniform-chunks", size, 4096)


def guards():
    result = source_hashes()
    result["benchmarks/compressed_trimmed_policy.py"] = hashlib.sha256(
        Path(__file__).read_bytes()
    ).hexdigest()
    result["native_binary"] = hashlib.sha256(
        Path(live._native.__file__).read_bytes()
    ).hexdigest()
    return result


def run(size=2**20, repeats=3):
    before = guards()
    rng = random.Random(724)
    records = []
    original = live.CompressedArray
    original_info = storage_harness.Store.info

    def graph_info(store):
        result = original_info(store)
        result["owned_bytes"] = retained_graph_bytes(store.data)
        return result

    storage_harness.Store.info = graph_info
    with pinned_baseline() as (base, source):
        trimmed = trimmed_class(base)
        try:
            for name, data in cases(size):
                operations = traces(data, 4096)
                methods = [
                    ("base-none", base, "palette-none"),
                    ("trim-none", trimmed, "palette-none"),
                    ("base-zstd", base, "palette-zstd"),
                    ("trim-zstd", trimmed, "palette-zstd"),
                    ("dense-lz4", base, "dense-lz4"),
                    ("dense-zstd", base, "dense-zstd"),
                ]
                samples = {name: [] for name, _, _ in methods}
                for _ in range(repeats):
                    rng.shuffle(methods)
                    for method, cls, backend in methods:
                        live.CompressedArray = cls
                        samples[method].append(
                            trial(data, backend, 4096, 65536, operations)
                        )
                records.append({"case": name, "samples": samples})
                print(
                    name,
                    {
                        method: {
                            "build_ms": statistics.median(x["build_ms"] for x in rows),
                            "cold_owned_bytes": rows[0]["initial_storage"][
                                "owned_bytes"
                            ],
                        }
                        for method, rows in samples.items()
                    },
                    flush=True,
                )
        finally:
            live.CompressedArray = original
            storage_harness.Store.info = original_info
    after = guards()
    assert before == after, "Measured sources changed during benchmark"
    return {
        "baseline_commit": BASELINE_COMMIT,
        "baseline_python_sha256": hashlib.sha256(source).hexdigest(),
        "source_sha256": before,
        "size": size,
        "repeats": repeats,
        "seed": 723,
        "records": records,
        "scope": "Pinned Python baseline + current native extension; prototype histogram and hot access are Python/NumPy. Common reachable retained graph accounting across all methods includes prototype slot metadata and excludes shared codec modules; not RSS. Exact scalar/block reads and post-update contents verified by common harness.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=2**20)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.size < 4096 or args.size % 4096 or args.repeats < 1:
        parser.error("size must be a positive multiple of4096; repeats>=1")
    Path(args.output).write_text(
        json.dumps(run(args.size, args.repeats), indent=2) + "\n"
    )
