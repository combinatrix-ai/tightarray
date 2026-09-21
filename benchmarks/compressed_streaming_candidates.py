"""Exact streaming candidate selection, isolated from production code."""

import argparse
import hashlib
import json
import platform
import random
import statistics
import textwrap
import time
from pathlib import Path

import blosc2
import numpy as np

from benchmarks.compressed_storage import dataset
from benchmarks.compressed_trimmed_policy import guards, pinned_baseline

BASELINE = "d3596fd9899797f9e1dede772fbc1fb03300d9bd"

TAIL = """
    direct_payload = _direct_payload(raw, direct_bits)
    indexed_payload = None
    if self._palette and len(colors) < 256 and palette_bits < direct_bits:
        indexed_payload = _native._pack_palette(raw, palette_bits, colors)

    # All uncompressed candidates precede every compressed candidate on ties.
    winner_payload, winner_palette = direct_payload, b""
    winner_flags, winner_size = direct_bits, len(direct_payload)
    if len(raw) < winner_size:
        winner_flags, winner_payload, winner_size = direct_bits | 32, raw, len(raw)
    if indexed_payload is not None and len(indexed_payload) + len(colors) < winner_size:
        winner_flags, winner_palette = palette_bits, colors
        winner_payload, winner_size = indexed_payload, len(indexed_payload) + len(colors)

    # best_size remains the separate structured/trim-aware codec pruning bound.
    for index in range(3 if indexed_payload is not None else 2):
        if index == 0:
            candidate_payload, candidate_palette, flags = direct_payload, b"", direct_bits
        elif index == 1:
            candidate_payload, candidate_palette, flags = raw, b"", direct_bits | 32
        else:
            candidate_payload, candidate_palette, flags = indexed_payload, colors, palette_bits
        if len(candidate_payload) < 64 or best_size < (
            self._blosc.MIN_HEADER_LENGTH + len(candidate_palette)
        ):
            continue
        payload = self._compress(candidate_payload, shuffle=index == 1)
        if len(payload) < len(candidate_payload):
            size = len(payload) + len(candidate_palette)
            best_size = min(best_size, size)
            if size < winner_size:
                winner_flags, winner_palette = flags | 16, candidate_palette
                winner_payload, winner_size = payload, size
    if structured is not None and len(structured) - 2 < winner_size:
        return structured
    if trim_plan is not None and trim_plan[-1] < winner_size + 2:
        return self._encode_trim(raw, trim_plan)
    return bytes((winner_flags, len(winner_palette))) + winner_palette + winner_payload
"""


def streaming_class(base, source):
    """Reuse pinned planning verbatim; replace allocation/selection only."""
    code = source.decode().split("    def _encode(self, raw:", 1)[1]
    code = "    def _encode(self, raw:" + code.split("    def _chunk_length", 1)[0]
    code = textwrap.dedent(code).split("    candidates = [", 1)[0]
    code = code.replace(
        'return _Chunk(len(raw), "packed", palette_bits, colors, payload).seal()',
        "return bytes((palette_bits, len(colors))) + colors + payload",
    ).replace(
        "return _Chunk(len(raw), mode, direct_bits, payload=payload).seal()",
        'return bytes((direct_bits | (32 if mode == "bytes" else 0), 0)) + payload',
    )
    namespace = dict(base._encode.__globals__)
    exec(compile(code + TAIL, __file__ + ":generated", "exec"), namespace)  # noqa: S102
    return type("StreamingCandidates", (base,), {"_encode": namespace["_encode"]})


def traced_encode(cls, raw, codec, fake_sizes=None):
    calls = []

    class Traced(cls):
        def _compress(self, payload, *, shuffle):
            calls.append((payload, shuffle))
            if fake_sizes is not None:
                return (
                    bytes([len(calls)]) * fake_sizes[(len(calls) - 1) % len(fake_sizes)]
                )
            return super()._compress(payload, shuffle=shuffle)

    array = Traced((), codec=codec)
    return array._encode(raw), calls


def cases(size=65536):
    rng = np.random.default_rng(8241)
    values = {}
    for bits, palette in ((3, False), (5, False), (8, False), (3, True), (5, True)):
        low = 256 - (1 << bits) if palette else 0
        values[f"{'palette' if palette else 'direct'}-{bits}"] = rng.integers(
            low, low + (1 << bits), size=size, dtype=np.uint8
        ).tobytes()
    values["local-two"] = dataset("local-two", size, 4096).tobytes()
    values["runs32"] = dataset("runs32", size, 4096).tobytes()
    values["periodic"] = (bytes(range(32)) * ((size + 31) // 32))[:size]
    span = bytearray(size)
    for start in range(0, size, 4096):
        span[start + 1792 : start + 2304] = rng.integers(
            32, size=512, dtype=np.uint8
        ).tobytes()
    values["span"] = bytes(span)
    return values


def trace(raw):
    rng = random.Random(8242)
    current = bytearray(raw)
    writes = []
    for _ in range(32):
        start = rng.randrange(len(raw) - 16 + 1)
        values = bytes(x ^ 1 for x in current[start : start + 16])
        assert all(
            a != b for a, b in zip(current[start : start + 16], values, strict=True)
        )
        current[start : start + 16] = values
        writes.append((start, values))
    return writes, bytes(current)


def timed(cls, raw, codec, writes, expected, calls):
    empty = cls((), codec=codec)
    begin = time.perf_counter_ns()
    for _ in range(calls):
        encoded = empty._encode(raw[:4096])
    encode_ns = (time.perf_counter_ns() - begin) / calls
    begin = time.perf_counter_ns()
    array = cls(raw, codec=codec, chunk_size=4096, cache_bytes=65536)
    build_ns = time.perf_counter_ns() - begin
    initial = tuple(array._chunks)
    assert array[0] == raw[0]
    begin = time.perf_counter_ns()
    for start, values in writes:
        array.write(start, values)
    array.flush()
    update_ns = time.perf_counter_ns() - begin
    final = tuple(array._chunks)
    assert array.tobytes() == expected
    assert array.storage_info().cache_bytes <= 65536
    array.clear_cache()
    assert array.tobytes() == expected
    return {
        "encode_ns": encode_ns,
        "build_ns": build_ns,
        "update_flush_ns": update_ns,
    }, (encoded, initial, final)


def source_guards():
    result = guards()
    root = Path(__file__).resolve().parents[1]
    for path in [Path(__file__), *(root / "tightarray").glob("_compressed*.h")]:
        result[str(path.relative_to(root))] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    return result


def run(repeats=11, calls=100):
    frozen = source_guards()
    rng = random.Random(8243)
    records = []
    with pinned_baseline(BASELINE) as (base, source):
        prototype = streaming_class(base, source)
        for name, raw in cases().items():
            writes, expected = trace(raw)
            for codec in ("none", "lz4", "zstd"):
                samples = {"baseline": [], "streaming": []}
                for _ in range(repeats):
                    order = [("baseline", base), ("streaming", prototype)]
                    rng.shuffle(order)
                    fingerprints = []
                    for policy, cls in order:
                        times, fingerprint = timed(
                            cls, raw, codec, writes, expected, calls
                        )
                        samples[policy].append(times)
                        fingerprints.append(fingerprint)
                    assert fingerprints[0] == fingerprints[1]
                # Instrument only outside timing, for every original chunk.
                total_calls = candidate_bytes = 0
                for start in range(0, len(raw), 4096):
                    original = traced_encode(base, raw[start : start + 4096], codec)
                    alternate = traced_encode(
                        prototype, raw[start : start + 4096], codec
                    )
                    assert original == alternate
                    total_calls += len(original[1])
                    candidate_bytes += sum(len(payload) for payload, _ in original[1])
                records.append(
                    {
                        "case": name,
                        "codec": codec,
                        "samples": samples,
                        "construction_compress_calls": total_calls,
                        "construction_candidate_bytes": candidate_bytes,
                        "median_ratio": {
                            key: statistics.median(v[key] for v in samples["streaming"])
                            / statistics.median(v[key] for v in samples["baseline"])
                            for key in samples["baseline"][0]
                        },
                    }
                )
                print(name, codec, "complete", flush=True)
    assert frozen == source_guards(), "Measured sources changed"
    return {
        "baseline": BASELINE,
        "pinned_python_sha256": hashlib.sha256(source).hexdigest(),
        "source_sha256": frozen,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "blosc2": blosc2.__version__,
        "repeats": repeats,
        "encode_calls_per_sample": calls,
        "size": 65536,
        "chunk_size": 4096,
        "cache_bytes": 65536,
        "changed_values_per_trial": 512,
        "records": records,
        "scope": "Pinned Python/current common native; same codec attempts, ordering and exact cold records. "
        "Balanced repeated trials in one process; encode is per4096-byte chunk, build/update+flush "
        "per65536-byte array. All codecs clevel5/typesize1/nthreads1. No production edits.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--repeats", type=int, default=11)
    parser.add_argument("--calls", type=int, default=100)
    args = parser.parse_args()
    if min(args.repeats, args.calls) < 1:
        parser.error("repeats and calls must be positive")
    Path(args.output).write_text(
        json.dumps(run(args.repeats, args.calls), indent=2) + "\n"
    )
