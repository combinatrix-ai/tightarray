"""Isolated exact-output direct8 packed-payload reuse experiment."""

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

BASELINE = "99377a7"


def inject(source):
    if "def _direct_payload(" in source:
        return source
    old = 'payload = _raw(Array(raw, bits=direct_bits)) if mode == "packed" else raw'
    new = 'payload = (_direct_payload(raw, direct_bits) if mode == "packed" else raw)'
    assert source.count(old) == 1
    source = source.replace(old, new)
    old = """        direct = Array(raw, bits=direct_bits, layout="packed")
        candidates = [
            _Chunk(len(raw), "packed", cast(_Bits, direct.bits), payload=_raw(direct)),
            _Chunk(len(raw), "bytes", cast(_Bits, direct.bits), payload=raw),
        ]"""
    new = """        candidates = [
            _Chunk(len(raw), "packed", direct_bits, payload=_direct_payload(raw, direct_bits)),
            _Chunk(len(raw), "bytes", direct_bits, payload=raw),
        ]"""
    assert source.count(old) == 1
    source = source.replace(old, new).replace(
        "if palette_bits < direct.bits:", "if palette_bits < direct_bits:"
    )
    source += """\n\ndef _direct_payload(raw, bits):
    if bits == 8:
        return raw if len(raw) % 8 == 0 else raw + bytes((-len(raw)) % 8)
    return _raw(Array(raw, bits=bits))
"""
    return source


def oracle_source(source):
    """Reverse live reuse calls to Array packing, without Git history in tests."""
    if "def _direct_payload(" not in source:
        return source

    class Reverse(ast.NodeTransformer):
        def visit_FunctionDef(self, node):
            if node.name == "_direct_payload":
                return None
            return self.generic_visit(node)

        def visit_Call(self, node):
            node = self.generic_visit(node)
            if isinstance(node.func, ast.Name) and node.func.id == "_direct_payload":
                return ast.Call(
                    func=ast.Name(id="_raw", ctx=ast.Load()),
                    args=[
                        ast.Call(
                            func=ast.Name(id="Array", ctx=ast.Load()),
                            args=[node.args[0]],
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
            name = "tightarray._direct8_trial_" + key
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
    rng = random.Random(888)
    for size in (4096, 4093):
        for name, alphabet in (
            ("direct8", tuple(range(256))),
            ("direct3", tuple(range(8))),
            ("direct5", tuple(range(32))),
            ("palette5", tuple(range(128, 160))),
        ):
            yield f"{name}-{size}", bytes(rng.choice(alphabet) for _ in range(size))
    yield "period8", bytes([128, 3, 225]) * 1365
    yield "runs8", b"\xff" * 1800 + b"\x80" * 300 + b"\xff" * 1996
    yield (
        "trim8",
        bytes(1792) + bytes(rng.randrange(256) for _ in range(512)) + bytes(1792),
    )


def run(repeats=7, operations=50):
    before = guards()
    own_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    rows = []
    rng = random.Random(484)
    with pair() as (modules, source):
        for name, raw in cases():
            pieces = (bytes(value ^ 1 for value in raw[3:19]), raw[3:19])
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
                                    arr.write(3, pieces[iteration % 2])
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
                                        raw[:3]
                                        + bytes(value ^ 1 for value in raw[3:19])
                                        + raw[19:]
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
