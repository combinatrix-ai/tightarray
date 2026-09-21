"""Delay period allocation only until RLE selection; benchmark-only prototype."""

import argparse
import ast
import hashlib
import json
import statistics
from pathlib import Path
from unittest.mock import patch

from benchmarks import compressed_lazy_period as prior
from tightarray import _core

BASELINE = "ffe172a"


def eager_source(source):
    """Reverse the adopted AST shape while preserving other source and comments."""
    tree = ast.parse(source)
    encode = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_encode"
    )
    assignments = [
        node
        for node in ast.walk(encode)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "period_selected"
    ]
    if not assignments:
        return source
    assert len(assignments) == 2
    false = next(
        node
        for node in assignments
        if isinstance(node.value, ast.Constant) and node.value.value is False
    )
    true = next(
        node
        for node in assignments
        if isinstance(node.value, ast.Constant) and node.value.value is True
    )
    branch = next(
        node
        for node in ast.walk(encode)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Name)
        and node.test.id == "period_selected"
    )
    trim = next(
        node
        for node in ast.walk(encode)
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "trim_plan"
        and isinstance(node.value, ast.IfExp)
    )
    lines = source.splitlines(keepends=True)
    body = lines[branch.body[0].lineno - 1 : branch.end_lineno]
    moved = [" " * 20 + line[12:] for line in body]
    changes = [
        (false.lineno - 1, false.end_lineno, []),
        (true.lineno - 1, true.end_lineno, moved),
        (branch.lineno - 1, branch.end_lineno, []),
        (
            trim.lineno - 1,
            trim.end_lineno,
            [
                "        trim_plan = _native._trim_plan(raw, colors, bool(self._palette), best_size + 2)\n"
            ],
        ),
    ]
    for start, end, replacement in sorted(changes, reverse=True):
        lines[start:end] = replacement
    return "".join(lines)


def after_rle_source(source, skip_trim=False):
    start = source.index("                    pattern = raw[:period]")
    end = source.index("                    best_size = period_size", start)
    materialize = source[start:end]
    source = (
        source[:start] + "                    period_selected = True\n" + source[end:]
    )
    source = source.replace(
        "        period_record = None\n",
        "        period_record = None\n        period_selected = False\n",
        1,
    )
    marker = (
        "        structured = run_record if run_record is not None else period_record"
    )
    assert source.count(marker) == 1
    moved = "\n".join(
        "            " + line[20:] for line in materialize.rstrip().splitlines()
    )
    source = source.replace(
        marker, "        elif period_selected:\n" + moved + "\n" + marker
    )
    if skip_trim:
        marker = "        trim_plan = _native._trim_plan(raw, colors, bool(self._palette), best_size + 2)"
        assert source.count(marker) == 1
        source = source.replace(
            marker,
            "        trim_plan = None if period_selected else _native._trim_plan(raw, colors, bool(self._palette), best_size + 2)",
        )
    return source


def policies_for(source):
    return {
        "eager": source,
        "after-rle": after_rle_source(source),
        "after-rle-skip-trim": after_rle_source(source, True),
    }


def run(oracle_only=False, repeats=21, iterations=128):
    own_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with (
        patch.object(prior, "BASELINE", BASELINE),
        patch.object(prior, "policies_for", policies_for),
    ):
        result = prior.run(
            repeats=repeats, iterations=iterations, oracle_only=oracle_only
        )
    # Count the work this variant actually avoids, including cases where a codec
    # later beats the RLE record. Codec losers without RLE still pack their period.
    data = prior.cases()
    for row in result["rows"]:
        raw = data[row["case"]]
        size = row["periodic_candidate_bytes"]
        avoided = False
        if size is not None:
            colors = bytes(sorted(set(raw)))
            direct_bits = max(1, colors[-1].bit_length())
            palette_bits = max(1, (len(colors) - 1).bit_length())
            palette = colors if row["palette"] and palette_bits < direct_bits else b""
            avoided = _core._rle_encode(raw, size - len(palette), palette) is not None
        row["full_delayed_materialization_opportunity"] = row.pop(
            "avoided_materialization"
        )
        row["avoided_materialization"] = avoided
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == own_hash
    result["after_rle_benchmark_sha256"] = own_hash
    result["scope"] = (
        "Pinned eager vs period allocation after failed RLE vs additional trim skip. Reuses previous exact-record/codec-input oracle; isolated _encode timings, not constructor/app E2E."
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--oracle-only", action="store_true")
    parser.add_argument("--repeats", type=int, default=21)
    parser.add_argument("--iterations", type=int, default=128)
    args = parser.parse_args()
    result = run(args.oracle_only, args.repeats, args.iterations)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    for row in result["rows"]:
        print(
            row["case"],
            row["palette"],
            row["codec"],
            row["winner"],
            row["avoided_materialization"],
            {
                key: round(statistics.median(values)) if values else None
                for key, values in row["encode_ns"].items()
            },
        )
