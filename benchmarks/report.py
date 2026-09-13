"""Render recorded benchmark JSON into Markdown and a per-method CSV."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs/results"
NAMES = ["python-list", "python-bytes", "python-str", "numpy", "packed", "word-aligned"]


def main():
    runs = [json.loads((RESULTS / name).read_text()) for name in ["m1-pro-numpy-interop.json"]]
    records = [row for run in runs for row in run["results"]]
    meta = runs[0]["metadata"]
    lines = ["# Measured performance", "", "Measured on Apple M1 Pro, ARM64 macOS, 2026-09-13.", "",
             f"CPython `{meta['python'].split()[0]}`, NumPy `{meta['numpy']}`; clang `-O3 -mcpu=apple-m1`.",
             "Medians of repeated adaptive timing batches. Each result is verified before timing.", "",
             "## Measurement boundaries", "",
             "- The machine was not isolated: existing services were left running; recorded load averages are in the JSON metadata. No affinity or cold-cache control was used.",
             "- Inputs are seeded uniform small integers; these are workload-specific results, not universal speedups.",
             "- `equal` measures native `.equals()` for tightarray and `np.array_equal` for NumPy; elementwise comparison and NumPy dispatch are measured separately in the NumPy API report.",
             "- `get` measures a single Python-level call; `random-get-sum` reads 256 prepared indices through Python and normalizes scalar values.",
             "- `iterate-sum` deliberately iterates in Python; it is not NumPy's native `sum` reduction.",
             "- `find` uses an eight-symbol repeated-maximum needle. An early match may end the scan. Do not compare search times across widths as equal amounts of work.",
             "- Python-list and NumPy `find` include conversion to bytes; bytes/str use their native search. tightarray includes needle construction.",
             "- `gather` uses prepared native `intp` buffers for NumPy and tightarray; `gather-list` passes the same Python list to both. Older JSON used different input formats and is not a matched gather baseline.",
             "- Nested construction uses the same Python rows for every implementation; NumPy ragged includes flattening and offsets construction.",
             "- Retained size counts owned buffers, object headers, shared objects once, and allocations kept alive by views. It is not RSS.",
             "- Additional peak bytes are measured separately with tracemalloc: PyMem and NumPy-tracked allocations are included; untracked system allocations are excluded.",
             "- View creation and copying are separate methods. An array view retains its full root allocation.", "",
             "Raw results: [current native methods](results/m1-pro-numpy-interop.json), [before NumPy integration](results/m1-pro-optimized.json), [previous small/medium](results/m1-pro.json), [previous large](results/m1-pro-large.json), [initial baseline](results/m1-pro-baseline.json).",
             "[Per-method CSV](results/methods.csv) includes dataset size, result retained size, additional peak bytes, sample variability, and timings.", "",
             "## Retained memory", "", "KiB, including representation overhead. Lower is better.", "",
             "| Structure | Elements | Bits | Python list | NumPy | Packed | Word-aligned |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for structure in ["1d", "matrix", "ragged"]:
        for n in sorted({r["elements"] for r in records}):
            for bits in [2, 5, 7]:
                rows = {r["implementation"]: r for r in records if r["structure"] == structure and r["elements"] == n and r["bits"] == bits and r["method"] == "construct"}
                values = [f"{rows[name]['dataset_retained_bytes']/1024:.2f}" for name in ["python-list", "numpy", "packed", "word-aligned"]]
                lines.append(f"| {structure} | {n:,} | {bits} | " + " | ".join(values) + " |")
    lines += ["", "For 1D, bytes/str use approximately one byte per element plus a single object header; see the CSV for exact sizes.",
              "Ragged offsets are an additional eight bytes per row boundary, so short rows reduce the relative packing benefit.", "", "## Per-method execution time", "",
              "Microseconds per operation. `—` means no corresponding supported case. Lower is better."]
    for structure in ["1d", "matrix", "ragged"]:
        for n in [1024, 65536, 1048576]:
            for bits in [2, 5, 7]:
                subset = [r for r in records if (r["structure"], r["elements"], r["bits"]) == (structure, n, bits)]
                names = NAMES if structure == "1d" else ["python-list", "numpy", "packed", "word-aligned"]
                methods = sorted({r["method"] for r in subset})
                lookup = {(r["method"], r["implementation"]): r for r in subset}
                lines += ["", f"### {structure}, {n:,} elements, {bits} bits", "",
                          "| Method | " + " | ".join(names) + " |", "| --- | " + " | ".join(["---:"] * len(names)) + " |"]
                for method in methods:
                    cells = [f"{lookup[method, name]['ns_op']/1000:.3f}" if (method, name) in lookup else "—" for name in names]
                    lines.append(f"| {method} | " + " | ".join(cells) + " |")
    baseline = json.loads((RESULTS / "m1-pro-baseline.json").read_text())["results"]
    old = {(r["structure"], r["elements"], r["bits"], r["implementation"], r["method"]): r for r in baseline}
    lines += ["", "## Optimization versus the initial C implementation", "",
              "65,536 elements; matched operations only. Initial source commit: `bc57700`.",
              "Nested construction is excluded because the initial NumPy baseline preflattened its input; the final runner corrects this.", "",
              "| Structure | Bits | Layout | Method | Initial µs | Final µs | Initial/final |", "| --- | ---: | --- | --- | ---: | ---: | ---: |"]
    for r in records:
        if r["elements"] != 65536 or r["implementation"] not in ("packed", "word-aligned"):
            continue
        if (r["structure"] == "1d" and r["method"] in ("count", "equal", "slice-copy", "find")) or (r["structure"] != "1d" and r["method"] == "get"):
            before = old[r["structure"], r["elements"], r["bits"], r["implementation"], r["method"]]["ns_op"]
            lines.append(f"| {r['structure']} | {r['bits']} | {r['implementation']} | {r['method']} | {before/1000:.3f} | {r['ns_op']/1000:.3f} | {before/r['ns_op']:.1f}× |")
    lines += ["", "## Remaining optimization targets", "",
              "- Packing construction has validation and conversion costs; bytes/str/NumPy construction can be faster.",
              "- Single-item list access and Python iteration remain strong baselines; not every method wins.",
              "- Word-aligned slices starting within a word require realignment when copied.",
              "- Long needles use KMP with linear worst-case complexity; more pattern distributions and lengths need measurement.",
              "- Skewed workloads, cold-cache scans, dense bit-width sweeps, and hardware-isolated measurements are not covered by this run.", ""]
    (ROOT / "docs/performance.md").write_text("\n".join(lines))
    columns = ["structure", "elements", "bits", "implementation", "method", "dataset_retained_bytes", "result_retained_bytes", "additional_peak_bytes", "ns_op", "ns_element", "min_ns_op", "max_ns_op", "loops"]
    with (RESULTS / "methods.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    print(f"Rendered {len(records)} method comparisons")


if __name__ == "__main__":
    main()
