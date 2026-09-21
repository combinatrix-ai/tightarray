# Real Rubik solver pruning-table substitution

This is actual end-to-end solving with the external [muodov/kociemba](https://github.com/muodov/kociemba/tree/e2690493b43921732960cd5eeee2b1ee91922a7b) two-phase solver, pinned at `e2690493b43921732960cd5eeee2b1ee91922a7b` (package 1.2.1). Only its four Python pruning tables and `search.getPruning` accessor change; its search, move tables, depth limit, and input cubes stay unchanged. The solver and GPL source are optional external dependencies, not vendored here.

The Python backend gets faster and uses less table memory, but **the library's default native C backend remains 26–66× faster than tightarray with Python search**. This is a useful Python integration result, not a claim to accelerate default kociemba.

## Results

Five repeats, rotated deterministic backend order, medians in milliseconds. Six deterministic scrambles, two seeds each at 8/12/16 moves; scramble length is not optimal solution distance. Search maximum depth is 24 and Python timeout 30 seconds. No timeouts occurred.

| Scramble | Original Python | Packed bytearray | Dense bytearray | NumPy uint8 | tightarray 4-bit | Default C | Python speedup |
|---|---:|---:|---:|---:|---:|---:|---:|
| 8, seed21 | 3.437 | 3.315 | 3.096 | 3.288 | 3.217 | 0.125 | 1.07× |
| 8, seed42 | 1.699 | 1.650 | 1.671 | 1.717 | 1.550 | 0.042 | 1.10× |
| 12, seed21 | 81.934 | 78.567 | 68.949 | 79.390 | 67.511 | 1.943 | 1.21× |
| 12, seed42 | 17.110 | 16.506 | 14.737 | 15.691 | 14.188 | 0.233 | 1.21× |
| 16, seed21 | 86.070 | 81.693 | 74.065 | 84.160 | 72.587 | 1.098 | 1.19× |
| 16, seed42 | 1200.744 | 1090.861 | 972.634 | 1119.853 | 956.434 | 29.334 | 1.26× |

Compared with dense bytearray, tightarray is about 1.7–7.8% faster in five cases, and 3.9% slower in the shortest seed21 case. Compared with NumPy it is faster in all six. Most speed benefit is eliminating Python nibble extraction, as the dense bytearray ablation demonstrates. Compactness does not imply universal lookup superiority.

Retained object-graph estimates for the **four pruning tables only**, with 4,031,686 logical nibble slots (including any unused final padding slot):

| Representation | Retained bytes |
|---|---:|
| Original Python packed lists | 17,194,904 |
| Packed bytearray, original nibble extraction | 2,083,704 |
| Dense bytearray | 4,031,914 |
| NumPy uint8 | 4,032,134 |
| tightarray packed 4-bit | 2,016,136 |

These are `sys.getsizeof` graph estimates with shared list integers counted once, not RSS, peak memory, or whole-solver memory. Unchanged move tables remain substantial. All variants coexist during timing. Packed bytearray comes close to tightarray's capacity; its extra retained allocation comes from incremental construction. Tightarray has half the retained table size of the direct bytearray/NumPy ablations and ~8.5× less than original lists.

Median adaptation time was 34.4ms for tightarray, 34.8ms for dense bytearray, 35.2ms for NumPy, and 50.8ms for packed bytearray. This includes unpacking existing lists; the original is a reference-only baseline. The recorded Python table import took 238ms. Solve timings exclude import, conversion, and C cache initialization. Original Python caches and C caches were bundled with the pinned source; no table generation was needed. This does not measure cold filesystem/process startup or amortize adaptation across solves.

All 180 timed solves returned valid solutions, verified by applying moves to the scrambled cube. All five Python variants returned identical move sequences for each input, and full table contents matched before solves. C solutions were independently validated, without requiring an identical search path.

## Reproduction and evidence

Install CFFI first, then install the pinned external source (installing before CFFI can accidentally produce the fallback-only package):

```sh
python -m pip install cffi future
python -m pip install 'git+https://github.com/muodov/kociemba.git@e2690493b43921732960cd5eeee2b1ee91922a7b'
PYTHONPATH=. python benchmarks/real_rubik.py --output docs/real-rubik-results.json --repeats 5
```

[Raw samples, cache/source/binary hashes, exact scrambles, and solutions](real-rubik-results.json) and [reproducer](../benchmarks/real_rubik.py). The script requires all 12 Python cache files and the C backend. These are warmed CPython 3.12/macOS arm64 measurements, not results from a million-cube batch or the separate 794MB optimal-solver table. The latter's long initial table build was avoided. The optional smoke tests check representation parity and real solver validity; they do not install dependencies.

The raw artifact's `script_sha256` identifies the measured, pre-format script (also retained temporarily at `/tmp/ta-real-rubik-measured.py`). The committed script was formatted after measurement; behavior did not change. `post_run_provenance` was attached after timing and records loaded tightarray package/native extension paths plus source/header/binary hashes. It is explicitly post-run evidence, not an unperformed before/after guard.

The fair already-packed baseline matters: tightarray is 1.03–1.16× faster than packed bytearray across all six solves, while both retain approximately the same 2MB payload. The original-list 8.5× memory reduction is predominantly removal of Python list overhead, not an 8.5× improvement over packed storage. Focused optional integration tests: **3 passed**.
