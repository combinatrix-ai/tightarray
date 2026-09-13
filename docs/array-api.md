# Python Array API

`tightarray.array_api` targets the **2025.12 Python Array API Standard**, including
its linalg and FFT extensions. Install with `pip install '.[array-api]'`.

```python
from tightarray import Array
from tightarray import array_api as xp

native = Array([0, 1, 2, 3] * 16, bits=2)
x = xp.reshape(xp.asarray(native), (8, 8))
assert x.__array_namespace__() is xp
assert x.storage_bits == 2
mask = x > 1
assert mask.storage_bits == 1
x[::-1, ::2][0, 0] = 255  # shared view; storage widens to 8 bits
```

## Storage and scope

The standard namespace has its own array object with 0D and arbitrary ND shape
semantics. `uint8` and `bool` retain native packed storage, with shared basic
slices and permutations. Width grows on assignment when necessary; every view
uses the same storage cell. Other integer widths, floats, and complex values use
NumPy storage. There is no retained Python object per element.

Numerical operations currently unpack, call NumPy, and repack uint8/bool results.
This establishes interoperable semantics, **not a speed claim for this adapter**.
The native Array/Matrix/RaggedArray API and its optimized kernels remain separate;
its [NumPy dispatch subset](numpy.md) is not full ndarray compatibility.
Ragged arrays are outside the rectangular Array API standard.

Converting a native Array copies and preserves its bit width and layout; this
isolates fixed-width native mutations from automatic width changes. Conversion
with `copy=False` rejects when copying is necessary. NumPy and DLPack cannot view
sub-byte elements directly. Packed exports unpack; DLPack `copy=False` raises
`BufferError`. Importing unpacked uint8/bool DLPack storage also requires a copy.

`storage_nbytes` reports packed root buffer bytes (shared by its views), or NumPy
view logical bytes for other dtypes. It excludes Python metadata and temporary
unpacked buffers; it is not a complete retained-memory measurement.

## Reproducible conformance checks

```sh
python -m pip install -e '.[test,array-api]' -r tests/array-api-requirements.txt
python -m pytest -q
PYTHON=python sh scripts/check-array-api.sh -q
```

The runner clones the unmodified official
[array-api-tests](https://github.com/data-apis/array-api-tests/tree/2026.09.08),
pinned to `ef5b39f1190d54dca0d9a12646033d2d123afdd5`, and verifies the spec submodule
`5f847a3858875c682ae901aa22b0413bf24be9da`. A dirty checkout is rejected. A local pytest plugin removes only the five
upstream `skip(reason="flaky")` markers for remainder checks; their test bodies
remain unchanged and failures fail CI.
`ARRAY_API_SUITE_DIR` may select an existing checkout. Dependencies are pinned;
Hypothesis property tests use derandomization with up to 100 examples per test.
Some upstream special-case tests call `example()` directly and remain randomized.
CI runs unit tests and this suite on Linux/macOS, Python 3.12/3.14, retaining reports.

Local ARM64 macOS validation: **1,380 passed, 5 skipped, 1 xfailed**. The five skips
are upstream flaky remainder cases. On a second M1 Pro / Python 3.14 environment,
the suite collected four fewer special cases and reported 1,376 passed, 5 skipped,
1 xfailed; its 252 unit tests also passed under ASan/UBSan. One narrowly identified expected failure is
listed in `tests/array-api-xfails.txt`: `test_dunder_dlpack` accepts BufferError
only for cross-device copies, but packed CPU storage also needs expansion.
The [standard DLPack copy contract](https://data-apis.org/array-api/2025.12/API_specification/generated/array_api.array.__dlpack__.html)
requires BufferError when `copy=False` cannot be honored. We test this refusal
locally instead of silently copying. No dtype exclusions or blanket skips are used.
The complete upstream DLPack test is marked xfail, so this is a known coverage gap,
not a claim that every case in that test passed.

Finite generated tests are evidence, not certification or a proof of complete
compatibility. The compact [validation report](results/array-api-2025.12.json)
records versions and exceptions. Full reports remain CI artifacts.

The five remainder checks were additionally exercised with four seeds and
1,000 successful generated cases per test per seed (20,000 total), with no
failures. They are now enabled in every CI conformance run; the results above
record the earlier baseline before this change.

## Shared-kernel validation

The shared logical-view and reduction implementation passes **281 unit tests** and
**1,385 upstream tests, 1 xfailed, 0 skipped** on CPython 3.12 / ARM64 macOS,
including the formerly flaky remainder tests. The existing DLPack exception is
unchanged. See [architecture](shared-kernels.md) and [performance](core-performance.md).

The C view/storage follow-up passes **293 unit tests** and retains the same
upstream conformance coverage and DLPack exception. Direct scalar slots, GC/subclass
lifetimes, tuple indexing, iteration, and all widening width pairs have regression
coverage; both NEON and portable builds are checked with sanitizers.
See [C view measurements](cview-performance.md).

The strided/axis reduction follow-up adds native default/uint64 sums over axes and
axis tuples. Negative strides, empty outputs, unaligned result buffers, and exact
allocation tails have regression coverage. Other accumulation dtypes retain the
NumPy fallback. See [reduction measurements](axis-performance.md) and
[tile accumulator measurements](tile-performance.md).

## Widening policy

Assignment that expands packed storage emits `StorageWideningWarning` before
allocation or mutation. The warning identifies the old/new widths and shared
root length. All views retain the shared storage. Standard Python warning
filters control display frequency; turning this warning into an error leaves
the values and storage unchanged.

```python
xp.set_strict(True)  # reject implicit widening in the current execution context
# x[0] = 31 raises xp.StorageWideningError if its storage is narrower than 5 bits
xp.set_strict(False)
with xp.strict():
    x[0] = 1  # succeeds if the value fits
```

`strict(False)` temporarily permits widening; nested contexts restore their
previous policy even after exceptions. ContextVar isolation applies to threads
and asynchronous contexts. Strict mode only governs storage widening; logical
dtype conversion and arithmetic rules do not change. Fitting assignments never
invoke the policy callback. The native fixed-width Array remains range checked.

Public stubs and a `py.typed` marker are shipped and checked with mypy.
See [static typing](typing.md). Logical dtype and mutable storage width remain
separate; `storage_bits` is runtime metadata, not a static bit-width parameter.
