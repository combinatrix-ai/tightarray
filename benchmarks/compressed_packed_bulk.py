"""Isolated three-binary codec-free packed bulk-write comparison."""

import argparse
import hashlib
import json
import os
import platform
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def fixtures(bits, palette, length):
    rng = random.Random(8310 + bits + 19 * palette)
    codes = bytes(rng.randrange(1 << bits) for _ in range(length))
    colors = bytes(range(256 - (1 << bits), 256)) if palette else b""
    return codes, colors


def replacement(old, bits, colors):
    low = colors[0] if colors else 0
    return bytes(low + ((value - low + 1) % (1 << bits)) for value in old)


def native_trial(bits, palette, layout, offset, width, calls=257):
    from tightarray._core import _Hot

    from tightarray import Array

    codes, colors = fixtures(bits, palette, 4096 + offset + 8)
    root = Array(codes, bits=bits, layout=layout)
    hot = _Hot(root[offset : offset + 4096], colors)
    start = 3 if offset else 0
    expected = bytearray(hot.read())
    old = bytes(expected[start : start + width])
    new = replacement(old, bits, colors)
    assert all(a != b for a, b in zip(old, new, strict=True))
    assert hot.try_write(start, new) and hot.try_write(start, old)
    pieces = [new if i % 2 == 0 else old for i in range(calls)]
    begin = time.perf_counter_ns()
    for value in pieces:
        assert hot.try_write(start, value)
    elapsed = time.perf_counter_ns() - begin
    expected[start : start + width] = pieces[-1]
    assert hot.read() == expected
    assert root[:offset].tobytes() == codes[:offset]
    assert root[offset + 4096 :].tobytes() == codes[offset + 4096 :]
    # Full logical root equality catches changes outside the written region too.
    physical_expected = bytearray(codes)
    physical_expected[offset + start : offset + start + width] = bytes(
        v - (colors[0] if colors else 0) for v in pieces[-1]
    )
    assert root.tobytes() == physical_expected
    return {
        "ns": elapsed / calls,
        "calls": calls,
        "changed_values": calls * width,
        "digest": sha(hot.read()),
        "root_digest": sha(root.tobytes()),
        "hot_bytes": hot.nbytes,
    }


def public_trial(bits, palette, offset, width, budget, calls=129):
    from tightarray.compressed import CompressedArray

    codes, colors = fixtures(bits, palette, 4096)
    raw = bytes(colors[x] for x in codes) if colors else codes
    array = CompressedArray(raw, codec="none", chunk_size=4096, cache_bytes=budget)
    start = 0 if width == 4096 else (3 if offset else 0)
    old = raw[start : start + width]
    new = replacement(old, bits, colors)
    assert all(a != b for a, b in zip(old, new, strict=True))
    assert array[start] == raw[start]
    pieces = [new if i % 2 == 0 else old for i in range(calls)]
    begin = time.perf_counter_ns()
    for value in pieces:
        array.write(start, value)
    updated = time.perf_counter_ns()
    array.flush()
    flushed = time.perf_counter_ns()
    expected = bytearray(raw)
    expected[start : start + width] = pieces[-1]
    assert array.tobytes() == expected
    info = array.storage_info()
    assert info.cache_bytes <= budget
    cold = sha(b"".join(bytes([x]) if isinstance(x, int) else x for x in array._chunks))
    array.clear_cache()
    assert array.tobytes() == expected
    return {
        "updates_ns": updated - begin,
        "flush_ns": flushed - updated,
        "total_ns": flushed - begin,
        "calls": calls,
        "changed_values": calls * width,
        "digest": sha(expected),
        "cold_digest": cold,
        "stored_bytes": info.stored_bytes,
        "hot_bytes": info.cache_bytes,
    }


def manifest(package):
    source = package.parent / "tightarray"
    paths = (
        list(source.glob("*.h"))
        + list(source.glob("*.c"))
        + list((package / "tightarray").glob("*.py"))
        + list((package / "tightarray").glob("*.so"))
    )
    return {str(p.relative_to(package.parent)): sha(p.read_bytes()) for p in paths}


def worker(package, output, trials):
    import tightarray._core as core

    import tightarray
    from tightarray import compressed

    package = Path(package).resolve()
    for module in (tightarray, core, compressed):
        assert Path(module.__file__).resolve().is_relative_to(package), module.__file__
    before = manifest(package)
    layouts = [(b, False) for b in range(1, 9)] + [(b, True) for b in range(1, 8)]
    specs = [
        ("native", bits, palette, layout, offset, width, 0)
        for bits, palette in layouts
        for layout in ("packed", "word-aligned")
        for offset in (0, 7)
        for width in (1, 8, 16, 64, 256, 1024)
    ]
    specs += [
        ("public", bits, palette, "packed", offset, width, 65536)
        for bits, palette in layouts
        for offset in (0, 7)
        for width in (1, 8, 16, 64, 256, 1024)
    ]
    specs += [
        ("public", bits, palette, "packed", 0, 4096, 65536) for bits, palette in layouts
    ]
    specs += [
        ("public", bits, palette, "packed", 7, width, budget)
        for bits, palette in ((3, False), (5, False), (3, True), (5, True), (8, False))
        for width in (64, 1024)
        for budget in (0, 512)
    ]
    random.Random(8311).shuffle(specs)
    records = []
    for kind, bits, palette, layout, offset, width, budget in specs:
        samples = []
        for _ in range(trials):
            if kind == "native":
                sample = native_trial(bits, palette, layout, offset, width)
            else:
                sample = public_trial(bits, palette, offset, width, budget)
            samples.append(sample)
        records.append(
            {
                "kind": kind,
                "bits": bits,
                "palette": palette,
                "layout": layout,
                "offset": offset,
                "width": width,
                "budget": budget,
                "samples": samples,
            }
        )
    assert before == manifest(package)
    Path(output).write_text(
        json.dumps(
            {
                "package": str(package),
                "loaded_core": core.__file__,
                "source_sha256": before,
                "python": platform.python_version(),
                "records": records,
            },
            indent=2,
        )
        + "\n"
    )


def run(packages, rounds=3, trials=5):
    root = Path(__file__).resolve().parents[1]
    script_hash = sha(Path(__file__).read_bytes())
    snapshots = {key: manifest(path) for key, path in packages.items()}
    python_sources = [
        {k: v for k, v in values.items() if k.endswith(".py")}
        for values in snapshots.values()
    ]
    assert python_sources[0] == python_sources[1] == python_sources[2]
    results = []
    with tempfile.TemporaryDirectory(prefix="ta-packed-bulk-workers-") as tmp:
        for round_index in range(rounds):
            names = list(packages)
            names = names[round_index % 3 :] + names[: round_index % 3]
            for name in names:
                output = Path(tmp) / (name + ".json")
                env = dict(
                    os.environ, PYTHONPATH=str(packages[name]) + os.pathsep + str(root)
                )
                subprocess.run(
                    [
                        sys.executable,
                        str(Path(__file__).resolve()),
                        "--worker",
                        str(packages[name]),
                        "--output",
                        str(output),
                        "--trials",
                        str(trials),
                    ],
                    cwd=tmp,
                    env=env,
                    check=True,
                )
                result = json.loads(output.read_text())
                result.update(variant=name, round=round_index)
                results.append(result)
                print(round_index, name, "complete", flush=True)
    for i in range(len(results[0]["records"])):
        reference = None
        for result in results:
            record = result["records"][i]
            fingerprints = [
                {k: v for k, v in sample.items() if not k.endswith("_ns") and k != "ns"}
                for sample in record["samples"]
            ]
            if reference is None:
                reference = fingerprints[0]
            assert all(value == reference for value in fingerprints), record
    assert snapshots == {key: manifest(path) for key, path in packages.items()}
    assert script_hash == sha(Path(__file__).read_bytes())
    return {
        "rounds": rounds,
        "trials": trials,
        "script_sha256": script_hash,
        "platform": platform.platform(),
        "results": results,
        "scope": "Codec-free only. Three independently imported binaries, identical Python. "
        "Rotated freshprocess order; warmed native calls and prewarmed public writes. "
        "Public updates/flush measured separately; construction/verification excluded. "
        "257 native or129 public alternating actualchanged writes pertrial. "
        "Exact data/neighbors/coldrecord/reload/capacity equality across variants.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--worker")
    parser.add_argument(
        "--root", type=Path, default=Path("/tmp/ta-packed-bulk-experiment")
    )
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--trials", type=int, default=5)
    args = parser.parse_args()
    if args.worker:
        worker(args.worker, args.output, args.trials)
    else:
        packages = {
            name: (args.root / name / "lib").resolve()
            for name in ("baseline", "candidate16", "candidate64")
        }
        Path(args.output).write_text(
            json.dumps(run(packages, args.rounds, args.trials), indent=2) + "\n"
        )
