"""Preserved periodic-storage policies with pinned Python implementations.

Historical JSON artifacts were copied unchanged from the earlier /tmp runs:
prototype, expanded-hot integration, and cyclic-hot integration. This portable
refactor did not produce them. Integrated historical `runs-none`/`runs-zstd` keys
are legacy labels from the RLE harness: they mean the periodic candidate, not an
RLE-only configuration. The cyclic measurement's compressed.py hash predates a
subsequent docstring-only change; historical hashes are deliberately preserved.

Future runs pin baseline Python compressed.py to aafc50b and integrated Python to
eff5443, with current compiled native helpers. `expanded` overrides only periodic
hot decoding on the pinned integrated class; it is not a complete historical
binary restoration. Git history and a compatible current native extension are
required. Source and extension hashes are checked before and after each run.
"""

import argparse
import hashlib
import json
import random
import statistics
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import tightarray.compressed as live
from benchmarks import compressed_rle_policy as loader
from benchmarks.compressed_codec_policy import extras
from benchmarks.compressed_storage import CASES, dataset, source_hashes, traces, trial
from tightarray import Array, _core

BASELINE = "aafc50b"
INTEGRATED = "eff5443"


@contextmanager
def pinned(commit):
    # Reuse the package-aware loader and its temporary-module cleanup.
    with (
        patch.object(loader, "BASELINE_COMMIT", commit),
        loader.pinned_baseline() as result,
    ):
        yield result


def expanded_decode(chunk, length):
    count = chunk[1]
    period = chunk[2 + count] + 1
    pattern = Array._from_packed_bytes(
        chunk, period, chunk[0] & 15, 3 + count
    ).tobytes()
    raw = (pattern * ((length + period - 1) // period))[:length]
    return _core._Hot(Array(raw, bits=chunk[0] & 15), chunk[2 : 2 + count])


def candidate_class(base, integrated, phase):
    if phase == "cyclic":
        return integrated
    if phase == "expanded":

        class Expanded(integrated):
            def _decode(self, chunk, length):
                if isinstance(chunk, bytes) and chunk[0] & 128:
                    return expanded_decode(chunk, length)
                return super()._decode(chunk, length)

        return Expanded
    if phase != "prototype":
        raise ValueError("unknown phase")

    class Prototype(base):
        def _encode(self, raw):
            candidate = super()._encode(raw)
            if isinstance(candidate, int):
                return candidate
            period = _core._byte_period(raw)
            if not period:
                return candidate
            pattern = raw[:period]
            colors = _core._byte_palette(pattern)
            bits = max(1, colors[-1].bit_length())
            palette_bits = max(1, (len(colors) - 1).bit_length())
            palette = b""
            if self._palette and palette_bits < bits:
                palette, bits = colors, palette_bits
                table = bytearray(256)
                for index, color in enumerate(colors):
                    table[color] = index
                pattern = pattern.translate(bytes(table))
            packed = Array(pattern, bits=bits)._word_view()[0].tobytes()
            encoded = (
                bytes([128 | bits, len(palette)])
                + palette
                + bytes([period - 1])
                + packed
            )
            return encoded if len(encoded) < len(candidate) else candidate

        def _decode(self, chunk, length):
            if isinstance(chunk, bytes) and chunk[0] & 128:
                return expanded_decode(chunk, length)
            return super()._decode(chunk, length)

    return Prototype


def provenance():
    result = source_hashes()
    root = Path(__file__).resolve().parents[1]
    for name in (
        "benchmarks/compressed_period_policy.py",
        "benchmarks/compressed_rle_policy.py",
        "benchmarks/compressed_codec_policy.py",
    ):
        result[name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
    result["loaded_native_extension"] = hashlib.sha256(
        Path(_core.__file__).read_bytes()
    ).hexdigest()
    return result


def run(phase, size=1 << 20, repeats=5):
    if size < 4096 or size % 4096 or repeats < 1:
        raise ValueError("size must be a positive multiple of4096 and repeats>=1")
    before = provenance()
    original = live.CompressedArray
    rng = random.Random(722)
    records = []
    with (
        pinned(BASELINE) as (base, baseline_source),
        pinned(INTEGRATED) as (integrated, integrated_source),
    ):
        candidate = candidate_class(base, integrated, phase)
        cases = [(name, dataset(name, size, 4096)) for name in CASES] + list(
            extras(size, 4096, True)
        )
        try:
            for name, data in cases:
                operations = traces(data, 4096)
                methods = [
                    ("base-none", base, "palette-none"),
                    ("period-none", candidate, "palette-none"),
                    ("base-zstd", base, "palette-zstd"),
                    ("period-zstd", candidate, "palette-zstd"),
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
                            "build_ms": statistics.median(x["build_ms"] for x in rows),
                            "global_ms": statistics.median(
                                x["global_scalar_ms"] for x in rows
                            ),
                            "cold_owned_bytes": rows[0]["initial_storage"][
                                "owned_bytes"
                            ],
                        }
                        for key, rows in samples.items()
                    },
                    flush=True,
                )
        finally:
            live.CompressedArray = original
    after = provenance()
    if before != after:
        raise RuntimeError(
            "source or loaded extension changed during benchmark; discard timings"
        )
    return {
        "phase": phase,
        "baseline_commit": BASELINE,
        "integrated_commit": INTEGRATED,
        "baseline_python_sha256": hashlib.sha256(baseline_source).hexdigest(),
        "integrated_python_sha256": hashlib.sha256(integrated_source).hexdigest(),
        "source_sha256_before": before,
        "source_sha256_after": after,
        "baseline_scope": "Pinned Python implementations with current native helpers and benchmark harness",
        "seed": 722,
        "repeats": repeats,
        "size": size,
        "records": records,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase", choices=("prototype", "expanded", "cyclic"), required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--size", type=int, default=1 << 20)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    result = run(args.phase, args.size, args.repeats)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
