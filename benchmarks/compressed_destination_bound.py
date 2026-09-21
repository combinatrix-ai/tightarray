"""Exactness oracle for private Blosc2 destination limits, not a speed benchmark."""

import argparse
import hashlib
import json
import random
from pathlib import Path

import blosc2

from benchmarks import compressed_codec_context, compressed_codec_policy
from benchmarks.compressed_codec_context import params
from benchmarks.compressed_codec_policy import candidates
from benchmarks.compressed_input_dispatch import source_guards
from tightarray.compressed import CompressedArray

LENGTHS = (
    63,
    64,
    65,
    127,
    128,
    129,
    255,
    256,
    257,
    511,
    512,
    513,
    4095,
    4096,
    4097,
    16383,
    16384,
    16385,
)
NO_FIT = "The result could not fit "


def patterns(n):
    rng = random.Random(819 + n)
    return {
        "random256": bytes(rng.randrange(256) for _ in range(n)),
        "random8": bytes(rng.randrange(8) for _ in range(n)),
        "random32": bytes(rng.randrange(32) for _ in range(n)),
        "period31": (bytes(rng.randrange(32) for _ in range(31)) * ((n + 30) // 31))[
            :n
        ],
        "runs": bytes((i // 37) % 32 for i in range(n)),
        "localtwo": bytes(203 if rng.randrange(2) else 249 for _ in range(n)),
        "spikes": bytes(255 if i % 251 == 17 else 0 for i in range(n)),
    }


def limited(schunk, raw, capacity):
    backing = bytearray(capacity + 16)
    backing[capacity:] = b"!" * 16
    view = memoryview(backing)[:capacity]
    try:
        size = schunk._prefilter_data(0, raw, view)
    except RuntimeError as error:
        status = "no-fit" if str(error) == NO_FIT else "unexpected-error"
        result = {"status": status, "error": str(error)}
        payload = None
    else:
        assert 0 < size <= capacity
        result = {"status": "ok", "size": size}
        payload = bytes(view[:size])
    assert backing[capacity:] == b"!" * 16, "destination tail overwritten"
    return result, payload


def check_candidate(raw, codec, shuffle, bound):
    settings = params(codec, shuffle)
    baseline = blosc2.compress2(raw, **settings)
    # One context for this individual case only, seeded as in the earlier exact
    # length-keyed SChunk study. Never retained beyond this function.
    schunk = blosc2.SChunk(
        chunksize=len(raw),
        data=raw,
        cparams=settings,
        dparams={"nthreads": 1},
        contiguous=False,
    )
    full, payload = limited(schunk, raw, len(raw) + blosc2.MAX_OVERHEAD)
    baseline_equal = payload == baseline
    trials = []
    for label, capacity in (
        ("size-minus-one", len(baseline) - 1),
        ("size-equal", len(baseline)),
        ("size-plus-one", len(baseline) + 1),
        ("winner-bound", max(1, bound)),
    ):
        result, payload = limited(schunk, raw, capacity)
        expected_fits = len(baseline) <= capacity
        result.update(
            label=label,
            capacity=capacity,
            expected_fits=expected_fits,
            false_negative=expected_fits and result["status"] != "ok",
            baseline_equal=payload == baseline if payload is not None else None,
        )
        if payload is not None:
            assert blosc2.decompress2(payload, nthreads=1) == raw
            result["sha256"] = hashlib.sha256(payload).hexdigest()
        trials.append(result)
    repeat, repeated_payload = limited(schunk, raw, len(raw) + blosc2.MAX_OVERHEAD)
    del schunk
    return {
        "payload_length": len(raw),
        "baseline_length": len(baseline),
        "baseline_sha256": hashlib.sha256(baseline).hexdigest(),
        "full_status": full,
        "full_equal": baseline_equal,
        "post_limits_full_equal": repeated_payload == baseline,
        "post_limits_full_status": repeat,
        "trials": trials,
    }


def run(lengths=LENGTHS):
    before = source_guards()
    own_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    dependency_hashes = {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (
            Path(compressed_codec_context.__file__),
            Path(compressed_codec_policy.__file__),
            Path(blosc2.blosc2_ext.__file__),
        )
    }
    records = []
    for n in lengths:
        for pattern, raw in patterns(n).items():
            available, _ = candidates(raw)
            if isinstance(available, int):
                continue
            # Existing none-codec winner includes structural records, so this is
            # a valid incumbent size, not an entropy estimate.
            plain = CompressedArray(raw, chunk_size=n, codec="none")
            record = plain._chunks[0]
            best = len(record) - 2 if isinstance(record, bytes) else 0
            for codec in ("lz4", "zstd"):
                running_best = best
                for index, candidate in enumerate(available):
                    bound = min(
                        len(candidate.payload) - 1,
                        running_best - len(candidate.palette),
                    )
                    for shuffle in (False, True):
                        result = check_candidate(
                            candidate.payload, codec, shuffle, bound
                        )
                        result.update(
                            logical_length=n,
                            pattern=pattern,
                            candidate=index,
                            mode=candidate.mode,
                            palette_length=len(candidate.palette),
                            codec=codec,
                            shuffle=shuffle,
                            actual_filter=shuffle == (candidate.mode == "bytes"),
                            incumbent_bound=bound,
                        )
                        records.append(result)
                        if result["actual_filter"] and result["baseline_length"] < len(
                            candidate.payload
                        ):
                            running_best = min(
                                running_best,
                                result["baseline_length"] + len(candidate.palette),
                            )
        print("length", n, "records", len(records), flush=True)
    assert all(
        hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
        for path, digest in dependency_hashes.items()
    )
    assert source_guards() == before
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == own_hash
    trials = [trial for row in records for trial in row["trials"]]
    summary = {
        "candidates": len(records),
        "full_mismatches": sum(not row["full_equal"] for row in records),
        "post_limit_full_mismatches": sum(
            not row["post_limits_full_equal"] for row in records
        ),
        "bounded_trials": len(trials),
        "false_negatives": sum(trial["false_negative"] for trial in trials),
        "successful_nonidentical": sum(
            trial["status"] == "ok" and not trial["baseline_equal"] for trial in trials
        ),
        "unexpected_errors": sum(
            trial["status"] == "unexpected-error" for trial in trials
        ),
    }
    return {
        "blosc2": blosc2.__version__,
        "source_sha256": before,
        "benchmark_sha256": own_hash,
        "dependency_sha256": dependency_hashes,
        "lengths": lengths,
        "summary": summary,
        "records": records,
        "scope": "Untimed private-API oracle. Fresh SChunk per candidate/filter/codec; context destroyed after full/bounded/full probes. No retained pool or memory-performance claim. Destination is writable with sentinel tail. winner-bound clamped to1 only for API probing; bounds<=0 would skip in real selection.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--small", action="store_true")
    args = parser.parse_args()
    result = run((63, 64, 65) if args.small else LENGTHS)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(result["summary"])
