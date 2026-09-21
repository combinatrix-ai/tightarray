"""Offline codec-policy tradeoffs; histogram heuristics have no size guarantee.

Historical JSON artifacts were measured by the earlier /tmp script, not this
portable refactor. It deliberately retains the Python sorted(set(raw)) alphabet
scan used for those timings; it does not measure the newer native scan. Existing
cases use compressed_storage.dataset seed812; adverse cases use seed681.
The main phase predates two periodic cases; conditional draws preserve its RNG
stream exactly. Timed encode includes candidate creation/selection and codecs;
verification/decode is outside timing. Payload excludes object/header overhead.
"""

import argparse
import json
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np

from benchmarks.compressed_storage import CASES, dataset
from tightarray import Array
from tightarray.compressed import CompressedArray, _bits, _raw, _restore

# Historical candidate model, deliberately local to this policy experiment.
_Mode = Literal["packed", "bytes"]
_Bits = Literal[1, 2, 3, 4, 5, 6, 7, 8]


@dataclass(frozen=True, slots=True)
class _Chunk:
    length: int
    mode: _Mode
    bits: _Bits
    palette: bytes = b""
    payload: bytes = b""
    compressed: bool = False

    @property
    def nbytes(self) -> int:
        return len(self.palette) + len(self.payload)

    def seal(self) -> bytes:
        # Two private descriptor bytes, then palette and payload. Uniform chunks
        # remain scalar ints. Avoid retaining a Python record per nonuniform chunk.
        flags = (
            self.bits
            | (16 if self.compressed else 0)
            | (32 if self.mode == "bytes" else 0)
        )
        return bytes((flags, len(self.palette))) + self.palette + self.payload


def candidates(raw):
    colors = bytes(sorted(set(raw)))
    if len(colors) == 1:
        return raw[0], None
    direct = Array(raw, bits=_bits(colors[-1]))
    out = [
        _Chunk(len(raw), "packed", direct.bits, payload=_raw(direct)),
        _Chunk(len(raw), "bytes", direct.bits, payload=raw),
    ]
    if len(colors) < 256 and _bits(len(colors) - 1) < direct.bits:
        table = bytearray(256)
        for i, c in enumerate(colors):
            table[c] = i
        arr = Array(raw.translate(bytes(table)), bits=_bits(len(colors) - 1))
        out.append(_Chunk(len(raw), "packed", arr.bits, colors, _raw(arr)))
    return out, colors


def encode(raw, store, policy):
    base, _colors = candidates(raw)
    if isinstance(base, int):
        return base, 0
    smallest = min(base, key=lambda c: c.nbytes)
    selected = [smallest]
    if policy == "exhaustive":
        selected = list(base)
    elif policy == "raw-only":
        selected = [base[1]]
    elif policy == "best+raw":
        selected = [smallest] + ([base[1]] if smallest is not base[1] else [])
    elif policy == "probe-smallest":
        selected = [smallest]
    elif policy in ("stats-once", "entropy-skip"):
        x = np.frombuffer(raw, dtype=np.uint8)
        counts = np.bincount(x, minlength=256)
        p = counts[counts > 0] / len(x)
        entropy = float(-(p * np.log2(p)).sum())
        repeats = float(np.mean(x[1:] == x[:-1]))
        lag16 = float(np.mean(x[16:] == x[:-16])) if len(x) > 16 else 0
        # Nominally iid nearly-full-width alphabets: unsafe heuristic by design.
        if (
            policy == "entropy-skip"
            and entropy > smallest.bits - 0.10
            and repeats < 0.2
            and lag16 < 0.2
        ):
            selected = []
        elif repeats > 0.4:
            selected = [base[1]]
    count = 0
    original_candidates = list(base)
    for c in selected:
        if len(c.payload) < 64:
            continue
        payload = store._compress(c.payload, shuffle=c.mode == "bytes")
        count += 1
        if (
            policy == "probe-smallest"
            and count == 1
            and len(payload) + len(c.palette) < 0.98 * smallest.nbytes
        ):
            selected.extend(x for x in original_candidates if x is not smallest)
        if len(payload) < len(c.payload):
            base.append(_Chunk(c.length, c.mode, c.bits, c.palette, payload, True))
    return min(base, key=lambda c: c.nbytes), count


def extras(size, chunk, followup=False):
    rng = np.random.default_rng(681)
    if followup:
        yield (
            "high-two-period31",
            np.resize(
                np.array([205, 249], dtype=np.uint8)[rng.integers(2, size=31)], size
            ),
        )
        yield (
            "threebit-period67",
            np.resize(rng.integers(8, size=67, dtype=np.uint8), size),
        )
    yield "cycle31", np.resize(np.arange(31, dtype=np.uint8), size)
    yield "high-cycle32", np.resize(np.arange(200, 232, dtype=np.uint8), size)
    x = rng.integers(32, size=size, dtype=np.uint8)
    x.reshape(-1, chunk)[:, chunk // 2 :] = 0
    yield "half-random-half-zero", x
    x = np.empty(size, dtype=np.uint8)
    for start in range(0, size, chunk):
        n = [2, 4, 8, 16, 32, 128][(start // chunk) % 6]
        x[start : start + chunk] = rng.integers(n, size=chunk, dtype=np.uint8) + (
            256 - n
        )
    yield "changing-high-alphabet", x
    yield (
        "skew8",
        rng.choice(np.arange(8, dtype=np.uint8), size=size, p=[0.8] + [0.2 / 7] * 7),
    )
    x = np.zeros(size, dtype=np.uint8)
    x[::37] = rng.integers(128, 256, size=len(x[::37]), dtype=np.uint8)
    yield "periodic-sparse-high", x


def decode(result, length, store):
    if isinstance(result, int):
        return bytes([result]) * length
    raw = store._decompress(result.payload) if result.compressed else result.payload
    if result.mode == "bytes":
        return raw
    values = _restore(raw, length, result.bits).tobytes()
    return (
        values.translate(result.palette.ljust(256, b"\0")) if result.palette else values
    )


def run(phase="followup", size=2**20, chunk=4096, repeats=2):
    if size <= 0 or chunk < 64 or size % chunk or repeats < 1:
        raise ValueError("Require positive size divisible by chunk >=64 and repeats>=1")
    policies = (
        ["exhaustive", "best+raw", "probe-smallest"]
        if phase == "followup"
        else ["exhaustive", "best-only", "raw-only", "stats-once", "entropy-skip"]
    )
    cases = [(name, dataset(name, size, chunk)) for name in CASES] + list(
        extras(size, chunk, phase == "followup")
    )
    rows = []
    for codec in ["lz4", "zstd"]:
        store = CompressedArray([], codec=codec)
        for name, data in cases:
            blocks = [data[i : i + chunk].tobytes() for i in range(0, size, chunk)]
            baseline = None
            for policy in policies:
                durations = []
                for _ in range(repeats):
                    tick = time.perf_counter()
                    results = [encode(raw, store, policy) for raw in blocks]
                    durations.append(time.perf_counter() - tick)
                sizes = []
                for raw, (result, calls) in zip(blocks, results):
                    sizes.append(0 if isinstance(result, int) else result.nbytes)
                    decoded = decode(result, len(raw), store)
                    assert decoded == raw
                if baseline is None:
                    baseline = sizes
                ratios = [s / max(1, b) for s, b in zip(sizes, baseline)]
                row = {
                    "codec": codec,
                    "case": name,
                    "policy": policy,
                    "seconds": statistics.median(durations),
                    "stored_bytes": sum(sizes),
                    "codec_calls": sum(x[1] for x in results),
                    "size_ratio": sum(sizes) / max(1, sum(baseline)),
                    "worst_chunk_ratio": max(ratios),
                    "exact": True,
                }
                rows.append(row)
                print(row, flush=True)
    return {
        "size": size,
        "chunk": chunk,
        "repeats": repeats,
        "phase": phase,
        "rows": rows,
        "dataset_seed": 812,
        "adverse_seed": 681,
        "alphabet_scan": "python-sorted-set",
        "note": "Observed size increases are not guarantees. NumPy policy statistics, where used, are included in encoding timings.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("main", "followup"), default="followup")
    parser.add_argument(
        "--output",
        required=True,
        help="New output path; historical JSON files are separate recorded runs",
    )
    parser.add_argument("--size", type=int, default=2**20)
    parser.add_argument("--chunk", type=int, default=4096)
    parser.add_argument("--repeats", type=int, default=2)
    args = parser.parse_args()
    result = run(args.phase, args.size, args.chunk, args.repeats)
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
