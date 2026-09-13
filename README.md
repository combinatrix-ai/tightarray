# tightarray

Compact small-integer arrays for CPython, initially targeting Apple M1 Macs.

Status: design and benchmark planning. No array implementation or performance results yet.
The name is provisional; package-name availability has not been checked.

## Goal

Store unsigned integers using 1–8 bits per element, with few Python objects and fast access through a C extension. The core is independent of DNA, amino acids, or any other domain-specific alphabet.

Measure memory use and performance per method against standard Python and NumPy. For sequence operations, include bytes and str as competitors. Faster operation is a goal to establish by measurement, not a current claim.

## Initial scope

- One-dimensional arrays.
- Rectangular matrices.
- Ragged arrays corresponding to lists of lists.
- CPython C extension optimized first for Apple M1 / ARM64.
- General N-dimensional arrays are a later extension.

Logical structure and physical layout are separate:

| Structure | Representation |
| --- | --- |
| 1D | Data buffer and element count |
| Matrix | Data buffer and row/column counts |
| Ragged | Data buffer and a native integer offsets buffer |
| Future ND | Data buffer, shape, and logical strides |

Do not retain one Python object per element or row. Construct row views only when requested; direct two-index access should avoid an intermediate Python row object. Public API names remain undecided.

## Storage candidates

- **Packed**: dense fixed-width bit stream; elements may cross machine-word boundaries.
- **Word-aligned**: fit whole elements into each 64-bit word, leaving unused tail bits. This does not mean aligning each element to a word.

Widths 1, 2, 4, and 8 divide a byte; widths 3, 5, 6, and 7 need special handling when densely packed. For example, a word-aligned 5-bit layout holds 12 elements per 64-bit word with 4 unused bits.

Prototype widths 2, 5, and 7 first. Specialize access kernels by width and layout. Use NEON where benchmarks justify it; do not assume vectorization helps scalar Python access.

## Development sequence

1. Prototype both layouts for widths 2, 5, and 7.
2. Verify correctness against an unpacked reference, especially boundary access.
3. Compare method-level time and memory against Python and NumPy.
4. Extend the shared storage engine to matrices and ragged arrays.
5. Finalize the public API and complete widths 1–8 based on results.

See [benchmark plan](docs/benchmarks.md). Licensing and public publication are pending decisions.
