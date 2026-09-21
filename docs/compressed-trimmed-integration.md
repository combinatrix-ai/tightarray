# Trimmed storage integration plan

This is an implementation plan, not an adopted format or measured performance
claim. The Python prototype first constructs the existing winning encoding and
then a trimmed encoding. Native recognition reduces scanning cost but leaves
those discarded allocations and duplicate span alphabet discovery in place.

## Lazy candidate selection

Use the global alphabet already computed by `CompressedArray._encode` to size
full packed, raw and palette candidates. Enumerate at most two default values:
the first and last byte. A default absent from both endpoints cannot omit any
edge, so its trimmed form cannot beat the corresponding existing full form with
its smaller descriptor. Uniform chunks keep their scalar representation.

Before scanning a candidate interior, bound its best possible encoded size. If
there are K global colors and the interior has m values, it retains at least
K-1 colors: trimming removes only the chosen default. Its maximum is at least
the largest global color unless that is the default, in which case it is at
least the second largest. With `bits(x) = max(1, x.bit_length())`, safe lower
bounds for a packed interior are:

- Direct: `8 * ceil(m * bits(minimum_maximum) / 64)`.
- Palette: `(K-1) + 8 * ceil(m * bits(K-2) / 64)`.

Add the proposed eight-byte trimmed descriptor and compare the minimum allowed
bound against the best complete encoded length. Reject ties to preserve the
existing candidate. If raw interiors are supported, include m as another bound.
These are optimistic bounds; they may permit a losing candidate but cannot
reject a winning one. They preserve the important case where removing a rare
high endpoint value reduces bit width throughout the remaining interior.

For surviving candidates, scan the interior alphabet once, determine exact
packed/palette size, and retain only a lazy plan with bounds, default, width and
palette. Compare total record lengths consistently, including descriptor bytes.
Use the best total length to tighten RLE's early rejection threshold, accounting
for its two-byte descriptor. For codec none, construct only the final winner;
do not call `_make_hot(span)` after independently discovering its alphabet.

Codec-backed encoding still evaluates every existing full direct/palette/raw
compressed candidate. An uncompressed lower bound cannot safely rule out a
better codec result. Initially the trimmed form can compete uncompressed, as in
the prototype, without implicitly adding another set of codec calls.

## Hot storage and verification

A native span entry should retain its interior packed Array and palette plus
scalar default and logical bounds, answer exterior reads directly, and expand
only on changed writes. Its retained-graph accounting must include owned fields
without double counting Array buffers. Failure ordering and cache-budget rules
must remain the same as existing periodic entries.

Verify candidate choice against an independent all-default oracle, boundary
width changes, distinct endpoints, partial chunks, zero/tiny cache budgets,
read slicing and writeback failures. Measure complete construction, local/global
reads and updates plus flush against both current storage and dense Blosc2.
Native recognition alone has not justified production adoption.
