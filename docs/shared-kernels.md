# Shared logical views and native reductions

The first architecture experiment keeps the packed and word-aligned storage formats
and moves selected operations onto common C kernels. Logical `uint8`/`bool` dtype
remains independent of physical bit width. No domain encoding is introduced.

## Implemented boundary

```text
Native Array.sum() ──────────────────┐
                                    ├── width/layout-specific C reduction
Array API sum(axis=None) ── C view ───┘
Array API conversion ────── C view ───── unpack only selected values
Array API assignment ───── C view ───── validate, then scatter in C
```

`_view.h` validates `(shape, element_strides, element_offset)` against the native
array before reading or writing. It supports scalar, empty, negative-stride,
noncontiguous, and repeated-element views, up to 64 dimensions. Footprint and
shape arithmetic use wide intermediates to reject overflow and invalid bounds.
An empty view may carry an offset outside storage, but never dereferences it.

These descriptors are currently parsed per operation. Array API shape/stride
metadata and the shared `_Storage` cell are still Python objects; this is not yet
a persistent C view type or a complete rewrite of every container. Native
Matrix/Ragged storage continues to use its existing flat array plus row metadata.

Scalar Array API reads address one packed element directly. Basic assignment
snapshots and casts only the selected values before mutating storage, preserving
overlap semantics and preventing partial writes on validation failure. Existing
Array API views follow a width increase through the shared storage cell. Width
growth still decodes and repacks the root; it is an explicit remaining O(n) path.
Advanced indexing continues through the NumPy fallback.

## Experiments and selected kernels

The first implementation decoded 1,024-byte stack blocks and summed with NEON.
This removed whole-array allocation, but its 5-bit packed sum still took about
11.9 µs for 65,536 elements. A second implementation folded adjacent bit fields
inside a 64-bit word and improved that to about 9.2 µs (aligned: 3.2 µs).

For width `b`, each word is a sequence of base-`2**b` digits. Masks and shifts
combine adjacent digit pairs into wider slots, repeatedly, until their sum is
in one slot. The widths are compile-time constants so the compiler simplifies
masks, divisions and boundary cases. Unused high lanes are masked out.

The final dispatcher uses:

- 1 bit: existing optimized population-count kernel.
- 2–7 bits: word-level digit folding. Aligned layouts consume physical words.
- Packed 3 bit: complete logical lane groups, including cross-word extraction.
- Packed 5/6/7 bit: eight byte-aligned logical values per load where bounds permit,
  with safe prefix/tail handling. This experiment helped those widths but slowed
  3-bit input, so it is not applied to 3-bit input.
- 8 bit: NEON byte reduction, or the portable C fallback.

No reduction path materializes a decoded array. Strided reduction specializes
readers by width/layout, avoiding a function-pointer call and coordinate division
per element. ND reduction traverses outer coordinates once per inner run.

The initial generic strided implementation regressed the 5-bit stride-3 workload
from roughly 25 µs to 42 µs. Specialized readers restored it to roughly 21 µs;
NumPy still wins that workload. Exact final measurements and reproduction commands
are in [the performance report](core-performance.md).

## Correctness and remaining experiments

Regression tests cover all eight widths and both layouts, shifted roots, word
and block boundaries, random values, reversed/transposed views, repeated strides,
empty/scalar descriptors, invalid bounds, atomic validation, shared-view widening,
and overlapping assignment. The official Array API suite is retained unchanged
apart from the existing narrow DLPack xfail and flaky-marker removal policy.

This stage does not change default layout, add a bitplane format, release the GIL,
or promise NumPy zero-copy representation. Next useful experiments are a persistent
C view/storage object to reduce scalar wrapper overhead, bounded-memory widening,
and strided/axis kernels. Blocked packing or bitplanes should be compared as
separate storage experiments with random access, scanning, and conversion costs
included; current measurements do not establish that either would be better.
