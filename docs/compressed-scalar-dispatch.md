# Scalar dispatch measurements

The adopted implementation checks the exact slice type, then calls a module-level
alias of `operator.index`. Slice cannot be subclassed; normal integers, NumPy
integers, custom `__index__` objects, booleans and integer subclasses retain their
normal index conversion. Negative bounds and slices retain the existing semantics.
The alias is typed without `Any`; unsupported keys still raise TypeError.

The [scalar reproducer](../benchmarks/compressed_scalar_dispatch.py) compares the
live implementation to pinned Python `65c7a89` with the same native extension.
Each measurement is 16,384 accesses, nine randomized paired repeats, over packed,
uniform and periodic data. Keys include negatives and four key types: exact int,
NumPy int64, custom index objects and int subclasses. All values/checksums are
verified. Data and trace seed: 897. The separate
[slice control](../benchmarks/compressed_slice_dispatch.py) uses 2,000 slices per
measurement, nine randomized repeats and seed 898. These are hot microbenchmarks,
not a new application or full Blosc2 comparison.

Three revisions were measured; raw artifacts retain their original hashes:

| Variant | Source commit | Outcome |
| --- | --- | --- |
| Exact int first | `dbfda7e` | Exact ints improve 6–12%, other key types regress 4–7%; rejected. |
| Index conversion first, TypeError fallback for slices | `2f19da2` | Scalars improve 7–14%, but contiguous slices regress 13–60%; rejected. |
| Exact slice first plus index alias | `7f087bd` | Scalars improve 4–11%; contiguous slices within about 1%, strided reads improve about 6%; adopted. |

Artifacts: [exact-int scalars](compressed-dispatch-exact-int-results.json),
[index-first scalars](compressed-dispatch-index-first-results.json),
[index-first slices](compressed-dispatch-slice-index-first-results.json),
[adopted scalars](compressed-dispatch-final-results.json),
[adopted slices](compressed-dispatch-slice-final-results.json).

To reproduce a historical variant, use that commit's implementation with the
corresponding benchmark script. All comparisons pin the pre-change Python baseline
and share the compiled native helpers; they do not restore a complete historical
binary environment. Source and extension hashes were unchanged during each run.
Individual percentage differences can vary with machine load and Python version.
No memory format, codec choice or cache admission behavior changed.

Focused storage tests passed on CPython 3.12 (84) and 3.14 (56, 28 optional-codec
skips), plus strict implementation typing and lint. Benchmarks additionally check
slice contents, bool indexing, out-of-bounds errors and int-subclass normalization.
