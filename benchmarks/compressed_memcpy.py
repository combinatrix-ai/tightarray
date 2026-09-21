"""Two-package native bulk-copy comparison with identical pinned Python files.

Snapshot the old extension before rebuilding. Run each package in a fresh worker
process; alternate randomized order. Startup/imports are outside timed regions.
"""

import argparse
import hashlib
import json
import os
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def native_trial(bits, palette, layout, offset, width, count=257):
    from tightarray._core import _Hot

    from tightarray import Array

    states = 1 << bits
    codes = bytes(i % states for i in range(4096 + offset + 8))
    colors = bytes(range(256 - states, 256)) if palette else b""
    source = Array(codes, bits=bits, layout=layout)
    hot = _Hot(source[offset : offset + 4096], colors)
    expected = bytearray(hot.read())
    start = 0 if width == 4096 else 13
    old = bytes(expected[start : start + width])
    if palette:
        new = bytes(colors[(colors.index(v) + 1) % states] for v in old)
    else:
        new = bytes((v + 1) % states for v in old)
    assert all(a != b for a, b in zip(old, new, strict=True))
    pieces = [new if i % 2 == 0 else old for i in range(count)]
    begin = time.perf_counter()
    for piece in pieces:
        assert hot.try_write(start, piece)
    elapsed = (time.perf_counter() - begin) * 1000
    expected[start : start + width] = pieces[-1]
    assert hot.read() == expected
    assert source[:offset].tobytes() == codes[:offset]
    assert source[offset + 4096 :].tobytes() == codes[offset + 4096 :]
    return {
        "ms": elapsed,
        "hot_payload": hot.nbytes,
        "changes": width * count,
        "calls": count,
    }


def worker(output):
    import tightarray._core as core

    import tightarray
    import tightarray.compressed as live
    from benchmarks.compressed_hot_bulk import cases, make_trace, trial

    layouts = [(8, False), (3, False), (5, False), (3, True), (5, True)]
    specs = [
        (bits, palette, layout, offset, width)
        for bits, palette in layouts
        for layout in ("packed", "word-aligned")
        for offset in (0, 7)
        for width in (1, 16, 64, 256, 4096)
    ]
    rng = random.Random(738)
    rng.shuffle(specs)
    native = []
    for bits, palette, layout, offset, width in specs:
        native.append(
            {
                "bits": bits,
                "palette": palette,
                "layout": layout,
                "offset": offset,
                "width": width,
                "sample": native_trial(bits, palette, layout, offset, width),
            }
        )
    public = []
    specs = [
        (name, budget, width, codec)
        for name in cases()
        if name.startswith(("direct", "palette"))
        for budget in (0, 65536)
        for width in (1, 16, 64, 256, 4096)
        for codec in ("none", "zstd")
    ]
    rng.shuffle(specs)
    data_cases = cases()
    for name, budget, width, codec in specs:
        data, labels = data_cases[name]
        writes, expected, changes = make_trace(data, labels, width, count=17)
        public.append(
            {
                "case": name,
                "budget": budget,
                "width": width,
                "codec": codec,
                "changes": changes,
                "sample": trial(
                    live.CompressedArray,
                    f"palette-{codec}",
                    data,
                    budget,
                    writes,
                    expected,
                ),
            }
        )
    package = Path(tightarray.__file__).parent
    result = {
        "native": native,
        "public": public,
        "package": str(package),
        "binary_sha256": hashlib.sha256(Path(core.__file__).read_bytes()).hexdigest(),
        "python_sha256": {
            str(p.relative_to(package)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in package.rglob("*.py")
        },
    }
    Path(output).write_text(json.dumps(result, indent=2) + "\n")


def hashes(package):
    package = Path(package) / "tightarray"
    return {
        str(p.relative_to(package)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in package.rglob("*")
        if p.is_file() and p.suffix in (".py", ".so")
    }


def run(baseline, candidate, repeats):
    root = Path(__file__).resolve().parents[1]
    sources = [
        Path(__file__),
        root / "benchmarks/compressed_hot_bulk.py",
        root / "benchmarks/compressed_span_bulk.py",
        root / "benchmarks/compressed_trimmed_policy.py",
        root / "benchmarks/compressed_storage.py",
        root / "tightarray/_core.c",
        root / "setup.py",
        *(root / "tightarray").glob("_compressed*.h"),
    ]

    def guards():
        return {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sources
        }

    before = guards()
    packages = {
        "base": str(Path(baseline).resolve()),
        "live": str(Path(candidate).resolve()),
    }
    manifests = {k: hashes(v) for k, v in packages.items()}
    py = [{k: v for k, v in h.items() if k.endswith(".py")} for h in manifests.values()]
    assert py[0] == py[1], "Python packages must match; isolate only native binary"
    rng = random.Random(739)
    samples = {k: [] for k in packages}
    with tempfile.TemporaryDirectory(prefix="ta-memcpy-workers-") as tmp:
        for repeat in range(repeats):
            order = list(packages)
            rng.shuffle(order)
            for label in order:
                output = Path(tmp) / f"{repeat}-{label}.json"
                env = dict(os.environ)
                env["PYTHONPATH"] = packages[label] + os.pathsep + str(root)
                subprocess.run(
                    [
                        sys.executable,
                        str(Path(__file__).resolve()),
                        "--worker",
                        "--output",
                        str(output),
                    ],
                    env=env,
                    cwd=tmp,
                    check=True,
                )
                samples[label].append(json.loads(output.read_text()))
                print(repeat, label, "complete", flush=True)
    assert before == guards()
    assert manifests == {k: hashes(v) for k, v in packages.items()}
    return {
        "python_commit": "6ea92e7",
        "repeats": repeats,
        "source_sha256": before,
        "package_sha256": manifests,
        "samples": samples,
        "scope": "Separate fresh processes for old/new native binaries with byte-identical pinned Python packages. Startup excluded. Native257-call batches, public17write+flush. 100native+100public configurations per worker. Packed/word-aligned, offset0/7 views; direct8 target and3/5/palettecontrols. Exact logical/bounds/cache checks; graphnotRSS. No dense comparison in this kernel isolation.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--baseline")
    parser.add_argument("--candidate")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.worker:
        worker(args.output)
    else:
        if not args.baseline or not args.candidate or args.repeats < 1:
            parser.error("baseline,candidate and positive repeats required")
        Path(args.output).write_text(
            json.dumps(run(args.baseline, args.candidate, args.repeats), indent=2)
            + "\n"
        )
