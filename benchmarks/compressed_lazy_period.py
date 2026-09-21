"""Lazy period materialization prototype; exact selection and codec trace oracle."""

import argparse
import hashlib
import json
import random
import statistics
import subprocess
import time
from pathlib import Path

from benchmarks.compressed_input_dispatch import modules, source_guards
from tightarray import _core

BASELINE = "faf98fd"


def lazy_source(source, winner_size="winner.nbytes"):
    start = source.index("                    pattern = raw[:period]")
    end = source.index("                    best_size = period_size", start)
    eager = source[start:end]
    materialize = eager.replace("period_record = (", "return (")

    def at(indent):
        return (
            "\n".join(
                " " * indent + line[20:] for line in materialize.rstrip().splitlines()
            )
            + "\n"
        )

    source = (
        source[:start] + "                    period_record = True\n" + source[end:]
    )
    source = source.replace(
        "        period_record = None\n", "        period_record = False\n", 1
    )
    source = source.replace(
        "        structured = run_record if run_record is not None else period_record",
        "        structured = run_record\n        period_pending = period_record and run_record is None",
        1,
    )
    source = source.replace(
        "            structured = None  # The span is strictly smaller, including headers.",
        "            structured = None  # The span is strictly smaller, including headers.\n            period_pending = False",
        1,
    )
    marker = "            if trim_plan is not None:\n                return self._encode_trim(raw, trim_plan)"
    assert source.count(marker) == 1
    source = source.replace(
        marker, "            if period_pending:\n" + at(16) + marker
    )
    marker = f"        if trim_plan is not None and trim_plan[-1] < {winner_size} + 2:"
    assert source.count(marker) == 1
    source = source.replace(
        marker,
        f"        if period_pending and period_size < {winner_size}:\n"
        + at(12)
        + marker,
    )
    return source


def skip_trim_source(source):
    marker = "        trim_plan = _native._trim_plan(raw, colors, bool(self._palette), best_size + 2)"
    assert source.count(marker) == 1
    return source.replace(
        marker,
        "        trim_plan = None if period_record else _native._trim_plan(raw, colors, bool(self._palette), best_size + 2)",
    )


def policies_for(source, winner_size="winner.nbytes"):
    return {
        "eager": source,
        "lazy": lazy_source(source, winner_size),
        "skip-trim": skip_trim_source(source),
        "combined": skip_trim_source(lazy_source(source, winner_size)),
    }


def cases():
    rng = random.Random(8109)
    patterns = {
        "random31": bytes(rng.randrange(32) for _ in range(31)),
        "high-two31": bytes(rng.choice((203, 249)) for _ in range(31)),
        "random67": bytes(rng.randrange(32) for _ in range(67)),
        "high-eight127": bytes(rng.randrange(248, 256) for _ in range(127)),
        "long-runs127": bytes(63) + bytes([255]) * 64,
        "spike251": bytes(250) + b"\xff",
        "ascending256": bytes(range(256)),
    }
    result = {}
    for name, pattern in patterns.items():
        for count in (2, 16):
            result[f"{name}-x{count}"] = pattern * count
    result["nonperiodic32"] = bytes(rng.randrange(32) for _ in range(4096))
    result["uniform"] = bytes(4096)
    return result


def instrument(base):
    class Traced(base):
        calls = None

        def _compress(self, raw, *, shuffle):
            self.calls.append((raw, shuffle))
            return super()._compress(raw, shuffle=shuffle)

    return Traced


def selected_period_size(raw, palette):
    colors = bytes(sorted(set(raw)))
    if len(colors) <= 1:
        return None
    bits = max(1, colors[-1].bit_length())
    pbits = max(1, (len(colors) - 1).bit_length())
    full = min(((len(raw) * bits + 63) // 64) * 8, len(raw))
    if palette and pbits < bits:
        full = min(full, ((len(raw) * pbits + 63) // 64) * 8 + len(colors))
    period = _core._byte_period(raw) if full > 9 else 0
    if not period:
        return None
    size = ((period * bits + 63) // 64) * 8 + 1
    if palette and pbits < bits:
        size = min(size, ((period * pbits + 63) // 64) * 8 + 1 + len(colors))
    return size if size < full else None


def run(repeats=7, iterations=64, oracle_only=False):
    before = source_guards()
    own_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    source = subprocess.check_output(
        ["git", "show", f"{BASELINE}:tightarray/compressed.py"],
        cwd=Path(__file__).resolve().parents[1],
    ).decode()
    records = []
    rng = random.Random(172)
    with modules(policies_for(source)) as policies:
        for name, raw in cases().items():
            for palette in (False, True):
                for codec in ("none",) if oracle_only else ("none", "lz4", "zstd"):
                    encoded = {}
                    traces = {}
                    for key, module in policies.items():
                        cls = instrument(module.CompressedArray)
                        cls.calls = []
                        arr = cls(
                            raw, chunk_size=len(raw), codec=codec, palette=palette
                        )
                        encoded[key] = arr._chunks[0]
                        traces[key] = cls.calls
                        assert arr.tobytes() == raw
                    assert all(value == encoded["eager"] for value in encoded.values())
                    assert all(value == traces["eager"] for value in traces.values())
                    cold = encoded["eager"]
                    winner = (
                        "uniform"
                        if isinstance(cold, int)
                        else "trim"
                        if cold[0] == 0
                        else "period"
                        if cold[0] & 128
                        else "runs"
                        if cold[0] & 64
                        else "codec"
                        if cold[0] & 16
                        else "ordinary"
                    )
                    size = selected_period_size(raw, palette)
                    samples = {key: [] for key in policies}
                    if not oracle_only:
                        for _ in range(repeats):
                            order = list(policies)
                            rng.shuffle(order)
                            for key in order:
                                arr = policies[key].CompressedArray(
                                    b"", codec=codec, palette=palette
                                )
                                start = time.perf_counter_ns()
                                for _ in range(iterations):
                                    result = arr._encode(raw)
                                samples[key].append(
                                    (time.perf_counter_ns() - start) / iterations
                                )
                                assert result == cold
                    records.append(
                        {
                            "case": name,
                            "logical_bytes": len(raw),
                            "palette": palette,
                            "codec": codec,
                            "winner": winner,
                            "periodic_candidate_bytes": size,
                            "avoided_materialization": size is not None
                            and winner != "period",
                            "codec_calls": len(traces["eager"]),
                            "cold_bytes": 0 if isinstance(cold, int) else len(cold),
                            "encode_ns": samples,
                        }
                    )
    assert source_guards() == before
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == own_hash
    return {
        "baseline_commit": BASELINE,
        "baseline_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "source_sha256": before,
        "benchmark_sha256": own_hash,
        "repeats": repeats,
        "iterations": iterations,
        "oracle_only": oracle_only,
        "rows": records,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--oracle-only", action="store_true")
    args = p.parse_args()
    result = run(oracle_only=args.oracle_only)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    for row in result["rows"]:
        print(
            row["case"],
            row["palette"],
            row["codec"],
            row["winner"],
            row["avoided_materialization"],
            {
                k: round(statistics.median(v)) if v else None
                for k, v in row["encode_ns"].items()
            },
        )
