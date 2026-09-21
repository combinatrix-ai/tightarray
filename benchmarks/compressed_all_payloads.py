"""Reuse native packing for every cold payload."""

import argparse
import ast
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

BASELINE = "2ba7a15"


def inject(source):
    if "_raw(Array(span, bits=bits))" not in source:
        assert "_direct_payload(span, bits)" in source
        return source
    replacements = {
        "_raw(Array(span, bits=bits))": "_direct_payload(span, bits)",
        "_raw(Array(pattern, bits=period_bits))": "_direct_payload(pattern, period_bits)",
        "indices = Array(raw.translate(bytes(translation)), bits=palette_bits)": "payload = _direct_payload(raw.translate(bytes(translation)), palette_bits)",
        "_raw(indices)": "payload",
    }
    for old, new in replacements.items():
        assert source.count(old) == (
            2 if old.startswith("indices") or old == "_raw(indices)" else 1
        )
        source = source.replace(old, new)
    return source


def oracle_source(source):
    if "_raw(Array(span, bits=bits))" in source:
        return source

    class Reverse(ast.NodeTransformer):
        def visit_Call(self, node):
            node = self.generic_visit(node)
            if isinstance(node.func, ast.Name) and node.func.id == "_direct_payload":
                raw = node.args[0]
                selected = isinstance(raw, ast.Name) and raw.id in ("span", "pattern")
                selected |= (
                    isinstance(raw, ast.Call)
                    and isinstance(raw.func, ast.Attribute)
                    and raw.func.attr == "translate"
                )
                if selected:
                    return ast.Call(
                        func=ast.Name(id="_raw", ctx=ast.Load()),
                        args=[
                            ast.Call(
                                func=ast.Name(id="Array", ctx=ast.Load()),
                                args=[raw],
                                keywords=[ast.keyword(arg="bits", value=node.args[1])],
                            )
                        ],
                        keywords=[],
                    )
            return node

    return ast.unparse(ast.fix_missing_locations(Reverse().visit(ast.parse(source))))


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
            name = "tightarray._all_payload_trial_" + key
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
