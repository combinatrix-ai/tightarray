"""Size arithmetic only: explicit hypothetical formats, no throughput claim."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from benchmarks.compressed_codec_policy import extras
from benchmarks.compressed_storage import CASES, dataset


def packed_size(values):
    if not len(values):
        return 0, 0, 0
    colors = np.unique(values)
    bits = max(1, int(colors[-1]).bit_length())
    direct = ((len(values) * bits + 63) // 64) * 8
    palette_bits = max(1, (len(colors) - 1).bit_length())
    indirect = ((len(values) * palette_bits + 63) // 64) * 8 + len(colors)
    # 256-entry palette is not encoded by the 1-byte palette count.
    if len(colors) < 256 and indirect < direct:
        return indirect, palette_bits, len(colors)
    return direct, bits, 0


def sizes(raw):
    counts = np.bincount(raw, minlength=256)
    default = int(counts.argmax())
    mask = raw != default
    positions = np.flatnonzero(mask)
    if not len(positions):
        return {"trim": 0, "bitmap": 0, "rle_bitmap": 0, "uniform": True}
    first, last = int(positions[0]), int(positions[-1]) + 1
    span = raw[first:last]
    exceptions = raw[mask]
    trim_payload, _trim_bits, trim_palette = packed_size(span)
    ex_payload, _ex_bits, ex_palette = packed_size(exceptions)
    edges = np.flatnonzero(mask[1:] != mask[:-1]) + 1
    run_lengths = np.diff(np.concatenate(([0], edges, [len(raw)])))
    run_bytes = sum(
        max(1, (int(length).bit_length() + 6) // 7) for length in run_lengths
    )
    # Header8: tag/default/bits/palette-count + two uint16 metadata fields.
    # RLE header adds first boolean + uint16 encoded-run-byte-count.
    result = {
        "trim": 8 + trim_payload,
        "bitmap": 8 + (len(raw) + 7) // 8 + ex_payload,
        "rle_bitmap": 11 + run_bytes + ex_payload,
        "uniform": False,
        "span": len(span),
        "exceptions": len(exceptions),
        "runs": len(run_lengths),
        "trim_palette": trim_palette,
        "exception_palette": ex_palette,
    }
    # Prove the representation's components retain the logical array exactly.
    reconstructed = np.full(len(raw), default, dtype=np.uint8)
    reconstructed[first:last] = span
    assert np.array_equal(reconstructed, raw)
    restored_mask = np.repeat(
        np.arange(len(run_lengths)) % 2 ^ int(mask[0]), run_lengths
    ).astype(bool)
    reconstructed[:] = default
    reconstructed[restored_mask] = exceptions
    assert np.array_equal(restored_mask, mask) and np.array_equal(reconstructed, raw)
    return result


def analyze(baseline_path):
    baseline = json.loads(Path(baseline_path).read_text())
    base = {row["case"]: row for row in baseline["records"]}
    size = baseline["size"]
    chunk = 4096
    rows = []
    for name, data in [(name, dataset(name, size, chunk)) for name in CASES] + list(
        extras(size, chunk, True)
    ):
        records = [
            sizes(data[start : start + chunk]) for start in range(0, size, chunk)
        ]
        proposed = {
            kind: sum(row[kind] for row in records)
            for kind in ("trim", "bitmap", "rle_bitmap")
        }
        standard = {}
        for kind in ["runs-none", "runs-zstd", "dense-zstd"]:
            info = base[name]["samples"][kind][0]["initial_storage"]
            descriptor_bytes = (
                0
                if kind == "dense-zstd"
                else 2 * (info["chunk_count"] - info["uniform_chunks"])
            )
            standard[kind] = info["stored_bytes"] + descriptor_bytes
        rows.append(
            {
                "case": name,
                "proposed_encoded_bytes": proposed,
                "current_encoded_bytes": standard,
                "best_proposed_perchunk_bytes": sum(
                    min(row[k] for k in proposed) for row in records
                ),
            }
        )
    return {
        "rows": rows,
        "chunk": chunk,
        "size": size,
        "baseline_artifact": Path(baseline_path).name,
        "baseline_sha256": hashlib.sha256(Path(baseline_path).read_bytes()).hexdigest(),
        "dataset_seed": 812,
        "adverse_seed": 681,
        "note": "Size arithmetic for explicit hypothetical layouts, not RSS or performance. Existing recorded baselines add two descriptor bytes per nonuniform chunk; dense codec headers already included. Proposed headers8/8/11 include default, bits, palette count, uint16 metadata. Packed values round to8-byte words; palettes included. Uniform uses existing zero-payload scalar representation. No current CompressedArray implementation is invoked.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "docs/compressed-rle-integrated-results.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.baseline)
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
