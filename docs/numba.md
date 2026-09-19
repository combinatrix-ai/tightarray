# Numba packed access and lattice simulation

The optional `tightarray.numba` module exposes fixed-width `Array` storage to
Numba without materializing uint8 values. It is an experimental explicit
**descriptor/helper API**, not automatic `@njit` compilation of `Array` or
Array API wrapper methods. Importing tightarray alone does not import Numba.

```sh
pip install -e '.[numba,test]'
```

```python
from numba import njit
from tightarray import Array
from tightarray.numba import as_native, load, store, specialize

values = Array([0, 1, 2, 3], bits=2)
native = as_native(values)  # Borrows packed words; retains the storage owner.

# Optional specialization makes width/layout constants in the generated code.
read, write = specialize(2, 'packed')

@njit
def advance(a):
    for i in range(a.length):
        write(a, i, (read(a, i) + 1) % 4)

advance(native)
assert list(values) == [1, 2, 3, 0]
# Generic load/store also work in @njit, without compile-time specialization.
# store(native, 0, 4) raises ValueError before changing either storage word.
```

The descriptor's `length` is the logical length: it is a named tuple of metadata,
so `len(native)` and `native[i]` are **not** logical array operations. Use
`native.length` and the access helpers. `specialize` validates the descriptor's
width/layout; it does not reuse a kernel compiled for a different width.

## Storage and mutation contract

- Values are unsigned integers, widths 1..8, with packed or word-aligned storage.
  Negative indices are normalized and out-of-bounds access raises IndexError.
- Writes outside the existing width raise ValueError; float values are rejected.
  No implicit widening takes place. An individual failed write does not mutate
  the target; a failure later in a user loop does not undo earlier writes.
- `as_native` accepts only fixed-size, fixed-width `tightarray.Array`. Automatic
  widening through the Array API layer is outside this interface.
- Contiguous slices keep their logical offset and root allocation alive. The
  physical NumPy uint64 view retains a private buffer exporter, which retains
  the owning Array. Deleting the original variable does not invalidate it.
- Do not construct/modify descriptors or mutate `words` directly. Those are
  physical storage fields. The helpers implement logical width and bounds checks.
- Packed writes are read-modify-write operations, not atomic. Different logical
  cells can share one word, so **do not put stores in a parallel `prange` loop**.
  Synchronize concurrent mutations, including external writes during reads.
- The core Array deliberately does not expose a public physical buffer protocol:
  NumPy conversion must still yield its logical values, not packed uint64 words.

## Worked application: cyclic cellular automaton

[examples/lattice.py](../examples/lattice.py) implements a 2D periodic grid. A cell
advances from `s` to `(s+1) % states` if at least one of its north/south/east/west
neighbors already has that next state. All reads use the previous generation;
updates use two separate buffers. States are fixed at construction, from 2 to 256.
This is a standalone simulation example, not a Mesa or CellPyLib plugin.

From a source checkout:

```python
import numpy as np
from examples.lattice import PackedGrid

initial = np.random.default_rng(7).integers(0, 4, (512, 512), dtype=np.uint8)
grid = PackedGrid(initial, states=4)
grid.step(100)
image = grid.to_numpy()  # Explicit decoding, e.g. for display.
print(grid.nbytes)      # Both packed grid buffers, not process RSS.
```

The example includes the same rule in NumPy and in Numba over uint8 arrays.
Tests compare all three with an independent Python implementation, including
1x1, one-row/column grids, odd dimensions, zero/odd/even step counts, and 2/3/4/8/
32/256 states. Core bridge tests cover all widths/layouts, cross-word writes,
slices, owner lifetimes, incorrect specialization and invalid writes.

## Measurement

```sh
python -m benchmarks.lattice --sizes 128 512 1024 --states 2 4 8 \
    --steps 10 --repeats 5 --output docs/results/lattice.json
```

[Raw results](results/lattice.json) retain every timing sample, package versions,
output hashes, payload sizes and traced update allocation peaks. Every timed
output is checked against the NumPy reference. Compile warmup is excluded; trial
order alternates. Construction (including initial encoding) and final decoding
are measured separately from updates. Grid payload counts **two backing buffers**;
Python/JIT metadata is excluded. A separate tracemalloc pass measures allocations
seen by that allocator, not complete native allocation or process RSS. Speedups
must not be inferred just from the storage ratio.

### Measured result: memory saving, not faster scalar updates

macOS arm64, Python 3.12.8, NumPy 2.5.3, Numba 0.67.0.
At 1024 x 1024 cells, ten synchronous steps (median of five trials):

| States | NumPy ms | Numba + uint8 ms | Numba + packed ms | Numba + aligned ms | Two packed grids MiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2 | 53.36 | 53.63 | 85.59 | 85.61 | 0.250 |
| 4 | 53.84 | 62.53 | 121.96 | 102.14 | 0.500 |
| 8 | 58.41 | 32.36 | 243.29 | 128.50 | 0.750 |

The two uint8 grids use 2 MiB in every row; packed backing buffers use 1/8,
1/4 and 3/8 as much for 2, 4 and 8 states. This is not a claim about process
RSS. The scalar packed updates lose on speed in this workload. Bit extraction,
checked access and read-modify-write stores add work; the uint8 Numba baseline
uses its default unchecked array access. Layout specialization is not a guarantee
of faster updates for every width. A next optimization should consider updating
multiple cells per machine word, rather than only translating scalar loops.

No speedup over an actual Mesa/CellPyLib application is claimed.

Validation for this change: 516 tests passed, including 60 bridge/lattice cases;
all 516 also passed with the C extension built under ASan/UBSan. Numba-generated
machine code itself is not automatically sanitizer-instrumented by that build.
The pinned Array API suite passed 1,385 tests with one existing expected failure.
Strict wheel-stub/consumer typing (including no-Any checks), source-archive
contents and a secret scan passed. CI includes native-access/grid tests on Linux
and macOS. These local measurements are from macOS arm64, not the CI hosts.
