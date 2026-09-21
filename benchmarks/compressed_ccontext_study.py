"""Experimental compression-only contexts: phases and normalized RSS."""

import argparse
import gc
import hashlib
import json
import random
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

from benchmarks import compressed_context_phases as phases
from benchmarks import compressed_shared_context as shared
from benchmarks.compressed_hot_bulk import cases, make_trace
from benchmarks.compressed_span_bulk_native import sized_trace


class NativeAdapter:
    def __init__(self, codec, raw, shuffle):
        from ta_ccontext import CompressionContext

        self.context = CompressionContext(codec, len(raw), shuffle)
        self.payload = self.context.compress(raw)

    def update_data(self, index, raw, *, copy):
        assert index == 0 and copy is False
        self.payload = self.context.compress(raw)

    def get_chunk(self, index):
        assert index == 0
        value = self.payload
        self.payload = b""
        return value

    @property
    def cbytes(self):
        return len(self.payload)


class NativePool(shared.SharedContextPool):
    def _new_context(self, codec, raw, shuffle):
        return NativeAdapter(codec, raw, shuffle)


@contextmanager
def pool_factory(module, factory):
    previous = module.SharedContextPool
    module.SharedContextPool = factory
    try:
        yield
    finally:
        module.SharedContextPool = previous


def guards():
    import blosc2
    import ta_ccontext

    result = phases.guards()
    for path in [
        Path(__file__),
        Path(ta_ccontext.__file__),
        *Path(__file__).with_name("native_context").glob("*.c"),
        Path(blosc2.__file__).parent / "lib/libblosc2.9.dylib",
    ]:
        result[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def timing(repeats):
    frozen = guards()
    rng = random.Random(1021)
    records = []
    for name, (data, labels) in cases().items():
        for budget in (512, 65536):
            for width in (16, 256):
                trace = sized_trace if name == "span-control" else make_trace
                writes, expected, changes = trace(data, labels, width, count=32)
                for codec in ("lz4", "zstd"):
                    modes = [
                        "adaptive",
                        "dense",
                        "shared-cold",
                        "shared-warm",
                        "native-cold",
                        "native-warm",
                    ]
                    samples = {mode: [] for mode in modes}
                    for _ in range(repeats):
                        rng.shuffle(modes)
                        for mode in modes:
                            if mode.startswith("native"):
                                with pool_factory(phases, NativePool):
                                    value = phases.trial(
                                        data,
                                        budget,
                                        codec,
                                        mode.replace("native", "shared"),
                                        writes,
                                        expected,
                                    )
                            else:
                                value = phases.trial(
                                    data, budget, codec, mode, writes, expected
                                )
                            samples[mode].append(value)
                    assert (
                        len(
                            {
                                s["cold_sha256"]
                                for mode in modes
                                if mode != "dense"
                                for s in samples[mode]
                            }
                        )
                        == 1
                    )
                    records.append(
                        {
                            "case": name,
                            "budget": budget,
                            "width": width,
                            "codec": codec,
                            "changes": changes,
                            "samples": samples,
                        }
                    )
    assert frozen == guards()
    return {"records": records, "source_sha256": frozen, "repeats": repeats}


def memory_worker(mode, count):
    gc.collect()
    before_import = shared.rss()
    import ta_ccontext

    assert ta_ccontext.CompressionContext
    after_import = shared.rss()
    factory = NativePool if mode == "native" else shared.SharedContextPool
    with pool_factory(shared, factory):
        row = shared.memory_worker(
            "compress2" if mode == "adaptive" else "shared", count
        )
    row.update(
        mode=mode,
        rss_before_native_import=before_import,
        rss_after_native_import=after_import,
        native_import_delta=after_import - before_import,
    )
    return row


def memory(repeats):
    frozen = guards()
    rng = random.Random(1022)
    records = []
    for count in (0, 16, 100, 500):
        for repeat in range(repeats):
            modes = ["adaptive", "shared", "native"]
            rng.shuffle(modes)
            for mode in modes:
                row = json.loads(
                    subprocess.check_output(
                        [
                            sys.executable,
                            "-m",
                            __spec__.name,
                            "--memory-worker",
                            mode,
                            str(count),
                        ],
                        text=True,
                    )
                )
                row["repeat"] = repeat
                records.append(row)
    assert frozen == guards()
    return {
        "records": records,
        "repeats": repeats,
        "source_sha256": frozen,
        "scope": "Each fresh worker imports the separate native dylib even for controls, then measures identical baseline/pool workloads. Native import delta reported separately. RSS deltas include allocators and native scratch. No context-only or production packaging claim.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    parser.add_argument("--repeats", type=int, default=31)
    parser.add_argument("--memory", action="store_true")
    parser.add_argument("--memory-worker", nargs=2)
    args = parser.parse_args()
    if args.memory_worker:
        print(
            json.dumps(memory_worker(args.memory_worker[0], int(args.memory_worker[1])))
        )
    else:
        if not args.output or args.repeats < 1:
            parser.error("output and positive repeats required")
        result = memory(args.repeats) if args.memory else timing(args.repeats)
        Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
