"""Run pinned upstream reverse Sokoban DFS, changing only visited-key encoding."""

import argparse
import ast
import hashlib
import json
import marshal
import platform
import random
import sys
import time
import types
from pathlib import Path
from statistics import median

import numpy as np

from tightarray import Array

COMMIT = "8e06e44e8bf3bb8bc73eeb1e7f0354508ce3fc89"
SOURCE = "/tmp/tightarray-sokoban-source/room_utils.py"
SOURCE_SHA256 = "2b4e9b6922d7d6322e6fdde0904e534f23855e41681ef3fea42eca68595292a7"


def encode(board, backend, fixed):
    if backend == "marshal":
        return marshal.dumps(board)
    if backend == "uint8":
        return board.astype(np.uint8).tobytes()
    if backend == "tightarray":
        return (
            Array(board.astype(np.uint8).reshape(-1), bits=3)._word_view()[0].tobytes()
        )
    if backend == "sparse":
        flat = board.reshape(-1)
        changed = np.flatnonzero(flat != fixed.reshape(-1))
        # Fixed shape <=65535 cells. Self delimiting 3-byte records: index + tile.
        records = np.empty((len(changed), 3), dtype=np.uint8)
        records[:, 0] = changed & 255
        records[:, 1] = changed >> 8
        records[:, 2] = flat[changed]
        return records.tobytes()
    raise ValueError(backend)


class KeyPatch(ast.NodeTransformer):
    def __init__(self, limit):
        self.limit = limit
        self.calls = self.limits = 0

    def visit_Call(self, node):
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "marshal"
            and node.func.attr == "dumps"
        ):
            self.calls += 1
            node.func = ast.Name(id="key_encoder", ctx=ast.Load())
        return self.generic_visit(node)

    def visit_Constant(self, node):
        if node.value == 300000:
            self.limits += 1
            return ast.copy_location(ast.Constant(value=self.limit), node)
        return node


def load_source(path, limit):
    source = Path(path).read_bytes()
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError("Upstream source hash mismatch")
    patch = KeyPatch(limit)
    tree = patch.visit(ast.parse(source))
    assert patch.calls == patch.limits == 1
    ast.fix_missing_locations(tree)
    module = types.ModuleType("sokoban_room_utils")
    exec(compile(tree, str(path), "exec"), module.__dict__)  # noqa: S102 - pinned hash-verified public source
    return module


def run_case(path, seed, backend, limit=5000, size=10, boxes=4):
    if size * size > 65535:
        raise ValueError("Sparse key index width exceeded")
    module = load_source(path, limit)
    random.seed(seed)
    np.random.seed(seed)
    tick = time.perf_counter()
    room = module.room_topology_generation((size, size), num_steps=40)
    room = module.place_boxes_and_player(room, boxes, False)
    fixed = room.copy()
    fixed[fixed == 5] = 1
    board = room.copy()
    board[board == 2] = 4
    calls = 0

    def key_encoder(value):
        nonlocal calls
        calls += 1
        return encode(value, backend, fixed)

    module.key_encoder = key_encoder
    result, score, mapping = module.reverse_playing(board, fixed)
    elapsed = time.perf_counter() - tick
    identity = {
        "visited": len(module.explored_states),
        "key_calls": calls,
        "score": int(score),
        "board_sha256": hashlib.sha256(result.astype(np.uint8).tobytes()).hexdigest()
        if result is not None
        else None,
        "mapping": sorted([[list(k), list(v)] for k, v in mapping.items()]),
    }
    identity["mapping"] = [
        [[int(x) for x in a], [int(x) for x in b]] for a, b in identity["mapping"]
    ]
    keys = module.explored_states
    return {
        "seed": seed,
        "backend": backend,
        "limit": limit,
        "size": size,
        "elapsed_s": elapsed,
        "key_payload_bytes": sum(map(len, keys)),
        "retained_key_set_bytes": sys.getsizeof(keys) + sum(map(sys.getsizeof, keys)),
        "identity": identity,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=SOURCE)
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", default="docs/results/real-sokoban-search.json")
    args = parser.parse_args()
    rows = []
    for seed in (11, 23, 37):
        by_backend = {name: [] for name in ("marshal", "uint8", "tightarray", "sparse")}
        reference = None
        for repeat in range(args.repeats):
            names = list(by_backend)
            if repeat % 2:
                names.reverse()
            for name in names:
                row = run_case(args.source, seed, name, args.limit)
                if reference is None:
                    reference = row["identity"]
                assert row["identity"] == reference
                by_backend[name].append(row)
        for name, trials in by_backend.items():
            row = trials[0].copy()
            row["elapsed_s"] = median(t["elapsed_s"] for t in trials)
            row["samples_s"] = [t["elapsed_s"] for t in trials]
            rows.append(row)
            print(row, flush=True)
    result = {
        "upstream_commit": COMMIT,
        "source_sha256": SOURCE_SHA256,
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "platform": platform.platform(),
        },
        "rows": rows,
    }
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
