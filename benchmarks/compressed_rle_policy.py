"""Compare historical and integrated RLE policies against pinned Python storage.

The checked-in compressed-rle-{rediscover,palette}-results.json files are unchanged
outputs from the earlier /tmp scripts, measured before production RLE integration;
this portable refactor did not produce them, and their hashes are not rewritten.
The integrated phase compares the current production class to the same baseline.

A new run loads only compressed.py from commit 0933f18, using the current native
Array/Hot/RLE helpers. Thus it isolates these historical Python policies, not an
entire historical build. Requires a Git checkout containing that baseline commit.
Use a fresh output path to retain the historical measurements.
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

import tightarray.compressed as live
from benchmarks.compressed_codec_policy import extras
from benchmarks.compressed_storage import CASES, dataset, source_hashes, traces, trial
from tightarray import Array, _core

BASELINE_COMMIT = "0933f18"


@contextmanager
def pinned_baseline():
    root = Path(__file__).resolve().parents[1]
    source = subprocess.check_output(
        ["git", "show", f"{BASELINE_COMMIT}:tightarray/compressed.py"], cwd=root
    )
    name = "tightarray._rle_policy_baseline"
    module = types.ModuleType(name)
    module.__package__ = "tightarray"
    previous = sys.modules.get(name)
    sys.modules[name] = module
    try:
        # Only this explicitly pinned repository baseline is executed.
        exec(compile(source, "baseline_compressed.py", "exec"), module.__dict__)  # noqa: S102
        yield module.CompressedArray, source
    finally:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous


def run_class(base, phase):
    if phase not in ("rediscover", "palette"):
        raise ValueError("phase must be rediscover or palette")

    class Runs(base):
        def _encode(self, raw):
            candidate = super()._encode(raw)
            if isinstance(candidate, int):
                return candidate
            if phase == "rediscover":
                payload = _core._rle_encode(raw, len(candidate) - 2)
                return bytes([64, 0]) + payload if payload is not None else candidate
            colors = _core._byte_palette(raw)
            bits = max(1, colors[-1].bit_length())
            palette_bits = max(1, (len(colors) - 1).bit_length())
            palette = b""
            encoded = raw
            if self._palette and palette_bits < bits:
                palette = colors
                bits = palette_bits
                translation = bytearray(256)
                for index, color in enumerate(colors):
                    translation[color] = index
                encoded = raw.translate(bytes(translation))
            payload = _core._rle_encode(encoded, len(candidate) - 2 - len(palette))
            return (
                bytes([64 | bits, len(palette)]) + palette + payload
                if payload is not None
                else candidate
            )

        def _decode(self, chunk, length):
            if isinstance(chunk, bytes) and chunk[0] & 64:
                if phase == "rediscover":
                    return self._make_hot(_core._rle_decode(chunk[2:], length))
                count = chunk[1]
                raw = _core._rle_decode(chunk[2 + count :], length)
                return _core._Hot(Array(raw, bits=chunk[0] & 15), chunk[2 : 2 + count])
            return super()._decode(chunk, length)

    return Runs


def run(phase, size=1 << 20, repeats=5):
    if size < 4096 or size % 4096 or repeats < 1:
        raise ValueError("size must be a positive multiple of 4096 and repeats >= 1")
    original = live.CompressedArray
    rng = random.Random(722)
    records = []
    with pinned_baseline() as (base, baseline_source):
        runs = original if phase == "integrated" else run_class(base, phase)
        cases = [(name, dataset(name, size, 4096)) for name in CASES] + list(
            extras(size, 4096, True)
        )
        try:
            for name, data in cases:
                operations = traces(data, 4096)
                methods = [
                    ("base-none", base, "palette-none"),
                    ("runs-none", runs, "palette-none"),
                    ("base-zstd", base, "palette-zstd"),
                    ("runs-zstd", runs, "palette-zstd"),
                    ("dense-lz4", base, "dense-lz4"),
                    ("dense-zstd", base, "dense-zstd"),
                ]
                samples = {key: [] for key, _, _ in methods}
                for _ in range(repeats):
                    rng.shuffle(methods)
                    for key, cls, backend in methods:
                        live.CompressedArray = cls
                        samples[key].append(
                            trial(data, backend, 4096, 65536, operations)
                        )
                records.append({"case": name, "samples": samples})
                print(
                    name,
                    {
                        key: {
                            "build": round(
                                statistics.median(x["build_ms"] for x in rows), 3
                            ),
                            "global": round(
                                statistics.median(x["global_scalar_ms"] for x in rows),
                                3,
                            ),
                            "cold": rows[0]["initial_storage"]["owned_bytes"],
                        }
                        for key, rows in samples.items()
                    },
                    flush=True,
                )
        finally:
            live.CompressedArray = original
    provenance = source_hashes()
    root = Path(__file__).resolve().parents[1]
    for name in (
        "tightarray/_compressed_rle.h",
        "tightarray/_compressed_hot.h",
        "tightarray/_core.c",
        "benchmarks/compressed_rle_policy.py",
        "benchmarks/compressed_codec_policy.py",
    ):
        provenance[name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
    return {
        "phase": phase,
        "baseline_commit": BASELINE_COMMIT,
        "baseline_python_sha256": hashlib.sha256(baseline_source).hexdigest(),
        "baseline_scope": "Pinned Python compressed.py with current native helpers and benchmark harness",
        "source_sha256": provenance,
        "seed": 722,
        "repeats": repeats,
        "size": size,
        "records": records,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase", choices=("rediscover", "palette", "integrated"), required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--size", type=int, default=1 << 20)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    result = run(args.phase, args.size, args.repeats)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
