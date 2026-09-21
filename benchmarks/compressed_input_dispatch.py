"""Paired input dispatch policies; isolated source modules, no production edits."""

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

from benchmarks.compressed_values_bytes import INSERTION, MARKER, guards

BASE = "ef925f5"
HELPER = "6ea92e7"
KINDS = ("bytes", "bytearray", "memoryview", "list", "tuple", "generator")


def sources(original, helper):
    assert INSERTION + MARKER not in original
    assert INSERTION + MARKER in helper
    line = "        raw = _values(values)"
    assert original.count(line) == 1
    write = original.replace(
        line, "        raw = values if type(values) is bytes else _values(values)"
    )
    containers = original.replace(
        line,
        "        kind = type(values)\n        if kind is bytes:\n            raw = values\n        elif kind is list or kind is tuple:\n            raw = bytes(iter(values))\n        else:\n            raw = _values(values)",
    )
    direct = containers.replace("raw = bytes(iter(values))", "raw = bytes(values)")
    typed = direct.replace(
        "            raw = values\n", "            raw = cast(bytes, values)\n"
    )
    return {
        "baseline": original,
        "helper-bytes": helper,
        "write-bytes": write,
        "write-containers": containers,
        "write-direct-containers": direct,
        "write-typed-containers": typed,
    }


@contextmanager
def modules(source_map):
    prior = {}
    loaded = {}
    try:
        for key, source in source_map.items():
            name = "tightarray._dispatch_" + key.replace("-", "_")
            prior[name] = sys.modules.get(name)
            module = types.ModuleType(name)
            module.__package__ = "tightarray"
            sys.modules[name] = module
            exec(compile(source, name, "exec"), module.__dict__)  # noqa: S102
            loaded[key] = module
        yield loaded
    finally:
        for name, value in prior.items():
            if value is None:
                del sys.modules[name]
            else:
                sys.modules[name] = value


def input_value(kind, raw):
    if kind == "bytes":
        return raw
    if kind == "bytearray":
        return bytearray(raw)
    if kind == "memoryview":
        return memoryview(raw)
    if kind == "list":
        return list(raw)
    if kind == "tuple":
        return tuple(raw)
    if kind == "generator":
        return (value for value in raw)
    raise ValueError(kind)


def source_guards():
    result = guards()
    result["dispatch_benchmark"] = hashlib.sha256(
        Path(__file__).read_bytes()
    ).hexdigest()
    return result


def run(repeats=11, operations=5000, cast_only=False):
    before = source_guards()
    root = Path(__file__).resolve().parents[1]
    original, helper = (
        subprocess.check_output(
            ["git", "show", f"{commit}:tightarray/compressed.py"], cwd=root
        ).decode()
        for commit in (BASE, HELPER)
    )
    rng = random.Random(3922)
    rows = []
    source_map = sources(original, helper)
    if cast_only:
        source_map = {
            key: source_map[key]
            for key in (
                "baseline",
                "helper-bytes",
                "write-direct-containers",
                "write-typed-containers",
            )
        }
    with modules(source_map) as policies:
        for size in (1, 16, 64, 256, 4096):
            generator = random.Random(14)
            raw = bytes(generator.randrange(32) for _ in range(size))
            for kind in KINDS:
                if not cast_only:
                    samples = {key: [] for key in policies}
                    value = input_value(kind, raw)
                    for _ in range(repeats):
                        order = list(policies)
                        rng.shuffle(order)
                        for key in order:
                            fn = policies[key]._values
                            start = time.perf_counter_ns()
                            if kind == "generator":
                                for _ in range(operations):
                                    output = fn(value for value in raw)
                            else:
                                for _ in range(operations):
                                    output = fn(value)
                            samples[key].append(
                                (time.perf_counter_ns() - start) / operations
                            )
                            assert output == raw
                    rows.append(
                        {
                            "operation": "helper",
                            "kind": kind,
                            "size": size,
                            "ns_per_operation": samples,
                        }
                    )
                # 8192-byte ordinary chunk: all tested writes are partial.
                initial = bytes(generator.randrange(32) for _ in range(8192))
                first = bytes((value + 1) % 32 for value in initial[:size])
                second = bytes((value + 2) % 32 for value in initial[:size])
                expected = second + initial[size:]
                samples = {key: [] for key in policies}
                for _ in range(repeats):
                    order = list(policies)
                    rng.shuffle(order)
                    for key in order:
                        arr = policies[key].CompressedArray(
                            initial, chunk_size=8192, cache_bytes=65536, codec="none"
                        )
                        arr.read()
                        payloads = (input_value(kind, first), input_value(kind, second))
                        start = time.perf_counter_ns()
                        if kind == "generator":
                            for n in range(128):
                                data = first if n % 2 == 0 else second
                                arr.write(0, (value for value in data))
                        else:
                            for n in range(128):
                                arr.write(0, payloads[n % 2])
                        arr.flush()
                        samples[key].append((time.perf_counter_ns() - start) / 128)
                        assert arr.tobytes() == expected
                rows.append(
                    {
                        "operation": "write-flush",
                        "kind": kind,
                        "size": size,
                        "ns_per_operation": samples,
                    }
                )
                print(
                    size,
                    kind,
                    {
                        key: round(statistics.median(values), 1)
                        for key, values in samples.items()
                    },
                    flush=True,
                )
    assert source_guards() == before, "measured source changed"
    return {
        "baseline_commit": BASE,
        "helper_commit": HELPER,
        "baseline_sha256": hashlib.sha256(original.encode()).hexdigest(),
        "helper_sha256": hashlib.sha256(helper.encode()).hexdigest(),
        "source_sha256": before,
        "repeats": repeats,
        "cast_only": cast_only,
        "operations": operations,
        "writes_per_flush": 128,
        "rows": rows,
        "scope": "Paired synthetic helper and warm 8192-byte ordinary partial writes; alternating payloads change every addressed value. Generators freshly created per call inside timing; mutable inputs prebuilt, no codec. Not app E2E.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=11)
    parser.add_argument("--operations", type=int, default=5000)
    parser.add_argument(
        "--cast-only",
        action="store_true",
        help="Compare original, helper, direct and typed write dispatch without helper microbenchmarks",
    )
    args = parser.parse_args()
    args.output.write_text(
        json.dumps(run(args.repeats, args.operations, args.cast_only), indent=2) + "\n"
    )
