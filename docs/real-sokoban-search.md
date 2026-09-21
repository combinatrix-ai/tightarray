# Real Sokoban search: visited-state memory tradeoff

This runs the actual reverse-play DFS from
[mpSchrader/gym-sokoban](https://github.com/mpSchrader/gym-sokoban/blob/8e06e44e8bf3bb8bc73eeb1e7f0354508ce3fc89/gym_sokoban/envs/room_utils.py),
pinned at `8e06e44e8bf3bb8bc73eeb1e7f0354508ce3fc89` (MIT license).
The source is downloaded separately, SHA256-verified, and is not vendored.
No Gym installation, renderer, or learned policy is used.

Two AST substitutions apply identically to every comparator: the one
`marshal.dumps(room_state)` call becomes a local key encoder, and the existing
300,000-state cap becomes 5,000. The upstream topology generator, box/player
placement, reverse-play search, scoring, recursion and action order run
unchanged. This measures actual procedural puzzle generation/search, not a
synthetic key-generation loop, but does not include the environment wrapper's
retry-until-positive-score behavior.

## Encodings

- **marshal:** original key serialization of the native-integer board.
- **uint8:** narrow to uint8 and store contiguous board bytes.
- **tightarray:** narrow to uint8, pack through the C buffer path at 3 bits,
  then use physical word bytes from `_word_view()[0].tobytes()`. Word-end
  padding is deterministic; a 100-cell board takes 40 bytes, not 100 bytes.
- **sparse:** sorted 3-byte records containing a uint16 position and uint8
  value for every cell differing from the shared fixed board. This captures
  all changed tile values, not merely a lossy box count.

The fixed board, shape and dtype are constant within each search. None of
these keys is a portable cross-level key format. Sparse indices are limited
to 65,535 cells. The canonical alternatives encode the same fixed-shape board
values; the recorded searches matched visited counts and outputs on the measured
interpreter. This is an experimental equivalence check, not a universal guarantee.
The active solver boards remain NumPy arrays for all comparators.

The original marshal baseline is intentionally unchanged. Its bytes need not be
canonical for equal board contents: CPython can set a reference flag according to
the object's reference count ([marshal writer implementation](https://github.com/python/cpython/blob/v3.14.0/Python/marshal.c#L353-L392)).
Python 3.14 CI exposed this difference between a retained board and a temporary
copy. Tests require marshal round-trips to preserve the board bytes, while the
three canonical alternatives also require identical keys for copied boards.
The actual-search comparison remains the integration check. Historical timings
and their interpreter provenance are retained without changing the baseline.

## Result

10×10 rooms, 4 boxes, topology generation with 40 steps, 3 seeds, 3 repetitions,
alternating backend order. Seed 37 reaches the 5,000-state cap with score 1,440:

| Key encoding | Full generation/search ms | Key bytes | Retained key set bytes |
|---|---:|---:|---:|
| Original marshal | 204.30 | 4,025,000 | 4,714,504 |
| uint8 bytes | **197.43** | 500,000 | 1,189,504 |
| tightarray 3bit bytes | 221.05 | 200,000 | 889,504 |
| Sparse position/value | 320.93 | **75,000** | **764,504** |

Tightarray saves about **25% of retained visited-set memory versus uint8**, at
about **12% more search time**. It is about 1.45× as fast as this sparse encoder,
using about 16% more retained-set memory. This is a real application tradeoff,
not an unconditional win: uint8 is faster, and sparse is smaller. Sparse key
construction here scans the board each time; an incrementally maintained
position key could improve it further.

Seed 11 exhausts 22 states and seed 23 exhausts 1,272; both have score zero.
They are retained as unsuccessful generation attempts rather than counted as
successful puzzle generation. All backends match visited count, key calls,
final board digest, score and box mapping on every seed/repetition. The saved
JSON has all results. Two focused tests also pass.

Retained-set bytes use `sys.getsizeof(set) + sum(sys.getsizeof(key))`, including
Python bytes headers and set table but excluding allocator fragmentation,
active recursion boards, fixed arrays and runtime imports. **This is not peak
RSS and does not demonstrate a process-memory-limit capacity frontier.**
Timing includes topology generation, placement, encoding, hashing, lookup and
search, but excludes loading/compiling the upstream source and reporting the
memory totals. Medians are warm process measurements with no JIT.

An initially tested int64-to-Array iterable path was unnecessarily slow; the
recorded result uses the uint8 C-buffer input, including conversion cost, just
as the uint8 baseline does. No core library changes were needed.

## Reproduce

Download `gym_sokoban/envs/room_utils.py` at the pinned commit to
`/tmp/tightarray-sokoban-source/room_utils.py`, retaining its adjacent upstream
license if copying the source elsewhere. Then:

```sh
python -m benchmarks.real_sokoban_search --limit 5000 --repeats 3
pytest -q tests/test_real_sokoban_search.py
```

The upstream integration test skips explicitly if this optional source has not
been downloaded. The source hash is checked before execution. The standalone
key-content test still runs without the upstream checkout.

[All measured results](results/real-sokoban-search.json)
