"""Actual kociemba solves; external GPL solver is installed separately, never vendored.
Install source e2690493b43921732960cd5eeee2b1ee91922a7b with CFFI available.
Only four pruning tables/accessor change; move tables and search remain upstream.
"""

from __future__ import annotations
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import platform
import random
import statistics
import sys
import time
import numpy as np
from tightarray import Array

PIN = "e2690493b43921732960cd5eeee2b1ee91922a7b"
NAMES = (
    "Slice_Flip_Prun",
    "Slice_Twist_Prun",
    "Slice_URFtoDLF_Parity_Prun",
    "Slice_URtoDF_Parity_Prun",
)


def direct(table, index):
    return table[index]


def apply_moves(cube, moves):
    from kociemba.pykociemba.cubiecube import moveCube

    for move in moves.split():
        face = "URFDLB".index(move[0])
        turns = 2 if move.endswith("2") else 3 if move.endswith("'") else 1
        for _ in range(turns):
            cube.multiply(moveCube[face])
    return cube


def cases():
    from kociemba.pykociemba.cubiecube import CubieCube

    result = []
    for count in (8, 12, 16):
        for seed in (21, 42):
            rng = random.Random(seed + count * 100)
            moves = []
            for _ in range(count):
                faces = [f for f in "URFDLB" if not moves or f != moves[-1][0]]
                moves.append(rng.choice(faces) + rng.choice(("", "2", "'")))
            scramble = " ".join(moves)
            result.append(
                {
                    "name": f"{count}moves-seed{seed}",
                    "scramble": scramble,
                    "facelets": apply_moves(CubieCube(), scramble)
                    .toFaceCube()
                    .to_String(),
                }
            )
    return result


def verify(case, solution):
    from kociemba.pykociemba.cubiecube import CubieCube

    assert not solution.startswith("Error"), solution
    cube = apply_moves(apply_moves(CubieCube(), case["scramble"]), solution)
    assert cube.toFaceCube().to_String() == CubieCube().toFaceCube().to_String()


def unpack(table):
    packed = np.asarray(table, dtype=np.int64).astype(np.uint8)
    values = np.empty(len(packed) * 2, dtype=np.uint8)
    values[::2] = packed & 15
    values[1::2] = packed >> 4
    return values


def adapt(original, policy):
    result = {}
    for name, table in original.items():
        if policy == "python-original":
            value = table
        elif policy == "packed-bytearray":
            value = bytearray(v & 255 for v in table)
        else:
            raw = unpack(table)
            if policy == "tightarray4":
                value = Array(raw.tobytes(), bits=4)
            elif policy == "dense-bytearray":
                value = bytearray(raw)
            else:
                value = raw
        result[name] = value
    return result


@contextmanager
def installed(tables, accessor):
    from kociemba.pykociemba import coordcube, search

    old = {n: getattr(coordcube.CoordCube, n) for n in NAMES}
    old_get = search.getPruning
    try:
        for name, table in tables.items():
            setattr(coordcube.CoordCube, name, table)
        search.getPruning = accessor
        yield
    finally:
        for name, table in old.items():
            setattr(coordcube.CoordCube, name, table)
        search.getPruning = old_get


def owned(tables):
    seen = set()

    def size(value):
        if id(value) in seen:
            return 0
        seen.add(id(value))
        return sys.getsizeof(value) + (
            sum(size(v) for v in value) if isinstance(value, list) else 0
        )

    return sum(size(v) for v in tables.values())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    import kociemba

    assert hasattr(kociemba, "lib"), "Native C backend required as control"
    cache = Path(kociemba.__file__).parent / "pykociemba" / "prunetables"
    assert len(list(cache.glob("*.pkl"))) == 12, "Refuse table generation"
    started = time.perf_counter()
    from kociemba.pykociemba import coordcube, search

    startup = time.perf_counter() - started
    originals = {n: getattr(coordcube.CoordCube, n) for n in NAMES}
    policies = (
        "python-original",
        "packed-bytearray",
        "dense-bytearray",
        "numpy-uint8",
        "tightarray4",
    )
    tables, build, memory = {}, {}, {}
    for policy in policies:
        times = []
        for _ in range(3):
            start = time.perf_counter()
            tables[policy] = adapt(originals, policy)
            times.append(time.perf_counter() - start)
        build[policy] = times
        memory[policy] = {
            "retained_graph_bytes": owned(tables[policy]),
            "logical_values": sum(len(v) * 2 for v in originals.values()),
        }
        for name in NAMES:
            expected = unpack(originals[name])
            value = tables[policy][name]
            if policy in ("python-original", "packed-bytearray"):
                assert np.array_equal(unpack(value), expected)
            else:
                assert bytes(value) == expected.tobytes()
    inputs = cases()
    samples = {p: {c["name"]: [] for c in inputs} for p in (*policies, "native-C")}
    solutions = {}
    # Warm C tables outside solve timing.
    verify(inputs[0], kociemba.solve(inputs[0]["facelets"], max_depth=24))
    for repeat in range(args.repeats):
        order = list(samples)
        random.Random(991 + repeat).shuffle(order)
        for policy in order:
            if policy == "native-C":
                for case in inputs:
                    start = time.perf_counter()
                    solution = kociemba.solve(case["facelets"], max_depth=24)
                    samples[policy][case["name"]].append(time.perf_counter() - start)
                    verify(case, solution)
                continue
            accessor = (
                coordcube.getPruning
                if policy in ("python-original", "packed-bytearray")
                else direct
            )
            with installed(tables[policy], accessor):
                for case in inputs:
                    start = time.perf_counter()
                    solution = (
                        search.Search()
                        .solution(case["facelets"], 24, 30, False)
                        .strip()
                    )
                    samples[policy][case["name"]].append(time.perf_counter() - start)
                    verify(case, solution)
                    assert solutions.setdefault(case["name"], solution) == solution
    root = Path(kociemba.__file__).parent
    hashes = {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
        and (p.suffix in (".py", ".pkl", ".so") or "cprunetables" in p.parts)
    }
    result = {
        "scope": "Actual warmed solver E2E; only pruning storage changed. C is default library backend, not modified.",
        "source_pin": PIN,
        "upstream": "https://github.com/muodov/kociemba",
        "python": sys.version,
        "platform": platform.platform(),
        "upstream_hashes": hashes,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "python_table_import_seconds": startup,
        "adaptation_seconds": build,
        "memory": memory,
        "memory_scope": "Four pruning tables only; retained graph excludes shared move tables and process RSS; all policies coexist during timing.",
        "cases": inputs,
        "solutions": solutions,
        "samples_seconds": samples,
        "median_seconds": {
            p: {c: statistics.median(v) for c, v in rows.items()}
            for p, rows in samples.items()
        },
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
