"""Fuse palette translation with native packed-payload construction."""

import argparse
import hashlib
import json
import random
import statistics
import subprocess
import sys
import time
import types
from contextlib import contextmanager
from pathlib import Path

from benchmarks.compressed_values_bytes import guards

BASELINE = "fa37aa2"


def inject(source):
    if "_native._pack_palette(" in source:
        return source
    for palette, target, indent in (
        ("palette", "span", 8),
        ("period_palette", "pattern", 12),
    ):
        pad = " " * indent
        block = (
            f"{pad}if {palette}:\n"
            f"{pad}    translation = bytearray(256)\n"
            f"{pad}    for index, color in enumerate({palette}):\n"
            f"{pad}        translation[color] = index\n"
            f"{pad}    {target} = {target}.translate(bytes(translation))\n"
        )
        assert source.count(block) == 1
        source = source.replace(block, "")
        bits = "bits" if target == "span" else "period_bits"
        old = f"_direct_payload({target}, {bits})"
        assert source.count(old) == 1
        source = source.replace(
            old,
            f"(_native._pack_palette({target}, {bits}, {palette}) if {palette} else {old})",
        )
    block = """                translation = bytearray(256)
                for index, color in enumerate(colors):
                    translation[color] = index
                payload = _direct_payload(
                    raw.translate(bytes(translation)), palette_bits
                )"""
    assert source.count(block) == 2
    return source.replace(
        block,
        "                payload = _native._pack_palette(raw, palette_bits, colors)",
    )


def oracle_source(source):
    if "_native._pack_palette(" not in source:
        return source
    return (
        source.replace("_native._pack_palette(", "_reference_palette_payload(")
        + """\n
def _reference_palette_payload(raw, bits, palette):
    translation = bytearray(256)
    for index, color in enumerate(palette):
        translation[color] = index
    return _direct_payload(raw.translate(bytes(translation)), bits)
"""
    )


@contextmanager
def pair(source=None):
    if source is None:
        source = subprocess.check_output(
            ["git", "show", f"{BASELINE}:tightarray/compressed.py"],
            cwd=Path(__file__).resolve().parents[1],
        ).decode()
    candidate = inject(source)
    baseline = oracle_source(source)
    modules = {}
    try:
        for key, text in (("baseline", baseline), ("reuse", candidate)):
            name = "tightarray._palette_pack_trial_" + key
            assert name not in sys.modules
            module = types.ModuleType(name)
            module.__package__ = "tightarray"
            sys.modules[name] = module
            modules[key] = module
            exec(compile(text, name, "exec"), module.__dict__)  # noqa: S102
        yield modules, source
    finally:
        for module in modules.values():
            del sys.modules[module.__name__]


def cases():
    rng = random.Random(8348)
    for count in (2, 8, 32, 128):
        alphabet = tuple(range(256 - count, 256))
        yield f"palette{count}", bytes(rng.choice(alphabet) for _ in range(4093))
    for length in (31, 127, 256):
        pattern = bytes(rng.randrange(128, 160) for _ in range(length))
        yield f"period{length}", (pattern * (4093 // length + 1))[:4093]
    for count in (8, 32, 128):
        inner = bytes(rng.randrange(256 - count, 256) for _ in range(509))
        yield f"trim-palette{count}", bytes(1791) + inner + bytes(1793)
    for bits in (3, 5, 8):
        inner = bytes(rng.randrange(1, 1 << bits) for _ in range(509))
        yield f"trim{bits}", bytes(1791) + inner + bytes(1793)
        yield f"direct{bits}", bytes(rng.randrange(1 << bits) for _ in range(4093))


def run(repeats=7, operations=50):
    before = guards()
    own_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    rows = []
    rng = random.Random(484)
    with pair() as (modules, source):
        for name, raw in cases():
            offset = 1800 if name.startswith("trim") else 3
            pieces = (
                bytes(value ^ 1 for value in raw[offset : offset + 16]),
                raw[offset : offset + 16],
            )
            for codec in ("none", "lz4", "zstd"):
                arrays = {
                    key: module.CompressedArray(b"", codec=codec)
                    for key, module in modules.items()
                }
                expected = arrays["baseline"]._encode(raw)
                assert arrays["reuse"]._encode(raw) == expected
                for phase in ("encode", "construct", "write-flush"):
                    samples = {key: [] for key in modules}
                    for _ in range(repeats):
                        order = list(modules)
                        rng.shuffle(order)
                        for key in order:
                            module = modules[key]
                            if phase == "write-flush":
                                arr = module.CompressedArray(
                                    raw, chunk_size=len(raw), codec=codec
                                )
                                arr.read()
                            start = time.perf_counter_ns()
                            for iteration in range(operations):
                                if phase == "encode":
                                    result = arrays[key]._encode(raw)
                                elif phase == "construct":
                                    arr = module.CompressedArray(
                                        raw, chunk_size=len(raw), codec=codec
                                    )
                                else:
                                    arr.write(offset, pieces[iteration % 2])
                                    arr.flush()
                            samples[key].append(
                                (time.perf_counter_ns() - start) / operations
                            )
                            if phase == "encode":
                                assert result == expected
                            else:
                                final = raw
                                if phase == "write-flush" and operations % 2:
                                    final = (
                                        raw[:offset] + pieces[0] + raw[offset + 16 :]
                                    )
                                assert arr.tobytes() == final
                                assert arr._chunks[0] == arrays["baseline"]._encode(
                                    final
                                )
                    rows.append(
                        {
                            "case": name,
                            "codec": codec,
                            "phase": phase,
                            "ns": samples,
                            "reuse_over_baseline": statistics.median(samples["reuse"])
                            / statistics.median(samples["baseline"]),
                        }
                    )
    assert before == guards()
    assert own_hash == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return {
        "baseline": BASELINE,
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "guards": before,
        "benchmark_sha256": own_hash,
        "repeats": repeats,
        "operations": operations,
        "rows": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--operations", type=int, default=50)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    Path(args.output).write_text(
        json.dumps(run(args.repeats, args.operations), indent=2) + "\n"
    )
