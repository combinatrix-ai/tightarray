"""Generate the tile report from reference-checked before/after runs."""
import json
import statistics
from pathlib import Path
root = Path(__file__).resolve().parents[1]
before = json.loads((root / 'docs/results/tiles-before.json').read_text())
after = json.loads((root / 'docs/results/tiles-after.json').read_text())
def key(r):
    return tuple(r[x] for x in ('bits', 'width', 'height', 'offset', 'layout', 'axis', 'library'))
b = {key(r): r for r in before['rows']}
a = {key(r): r for r in after['rows']}
assert len(a) == len(b) == 1440 and a.keys() == b.keys()
text = '''# Narrow tile accumulators and row dispatch

Baseline: e3e0605. Apple M1 Pro, CPython 3.13.15, NumPy 2.5.3.
The baseline was measured in two batches (bits 1/3/5/8 and 2/4/6/7).
Both revisions use the same deterministic random inputs, approximately 65,536
values per matrix, ten widths (16–1,024), and offsets 0, 1, and 7.
Each timing is the median of seven calibrated samples. Construction is excluded;
Array API timings include conversion of the reduction output to NumPy.
Every output is checked against NumPy uint64 sum. Thread counts are set to one.
These are warm-cache microbenchmarks, not a universal speed guarantee.

Column sums accumulate into uint16 when rows × maximum value fits; otherwise
uint32 batches are flushed into uint64 before overflow. A column tile uses at
most 1 KiB decoded bytes plus 4 KiB accumulators on the stack, in addition to
view descriptors. No full-size input expansion is introduced. Row dispatch uses
bit-width/layout limits and preserves word-folding paths for aligned rows where
the tile experiment regressed. The limits are conservative M1 measurements,
not an exhaustive search of every shape or other CPU.

## Aggregate results

| Reduction | Median old/new ratio | Cases slower by more than 10% | Cases |
|---|---:|---:|---:|
'''
for axis in (0, 1):
    rows = [r for r in a.values() if r['library'] == 'array-api' and r['axis'] == axis]
    ratios = [b[key(r)]['ns'] / r['ns'] for r in rows]
    text += f"| {'Column' if axis == 0 else 'Row'} sum | {statistics.median(ratios):.2f}× | {sum(v < 1/1.1 for v in ratios)} | {len(rows)} |\n"
text += '\n## Example: packed 5-bit, offset zero\n\n| Columns | Axis | Before µs | After µs | NumPy µs |\n|---:|---|---:|---:|---:|\n'
for r in a.values():
    if r['bits'] == 5 and r['layout'] == 'packed' and r['offset'] == 0 and r['library'] == 'array-api' and r['width'] in (33, 64, 128, 256):
        n = dict(r, library='numpy')
        text += f"| {r['width']} | {r['axis']} | {b[key(r)]['ns']/1000:.2f} | {r['ns']/1000:.2f} | {a[key(n)]['ns']/1000:.2f} |\n"
text += '\n## Remaining regressions (>10% slower)\n\n| Bits | Layout | Width | Offset | Axis | Old/new ratio |\n|---:|---|---:|---:|---:|---:|\n'
for r in a.values():
    ratio = b[key(r)]['ns'] / r['ns']
    if r['library'] == 'array-api' and ratio < 1/1.1:
        text += f"| {r['bits']} | {r['layout']} | {r['width']} | {r['offset']} | {r['axis']} | {ratio:.2f}× |\n"
if not any(r['library'] == 'array-api' and b[key(r)]['ns']/r['ns'] < 1/1.1 for r in a.values()):
    text += '| — | None observed in this run | — | — | — | — |\n'
text += '''
Earlier candidate runs showed small-width losses, which did not exceed 10%
in the final run. This variation needs repeated-run study. Timing variation and
separate baseline batches also affect small differences. Large-stride and ND
traversal were not changed in this experiment. Heap tracing in the raw results
does not include C stack buffers or represent total process memory.

Tests cover every bit width/layout, 16-to-32-bit accumulator boundaries,
column tile tails, row dispatch boundaries, negative/stepped row strides, and
an actual uint32 batch overflow boundary using a zero-stride repeated-row view.

Reproduce with `benchmarks/tile_experiment.py --label LABEL --output FILE`
against each installed revision, then run this report script. Raw results:
[before](results/tiles-before.json), [after](results/tiles-after.json).
'''
(root / 'docs/tile-performance.md').write_text(text)
