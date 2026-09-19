# CellPyLib E2E pilot

This is a real `cellpylib.evolve2d` API comparison, not the standalone cyclic
simulation. The experimental adapter in `examples/cellpylib_backend.py`
accelerates the official `game_of_life_rule` for binary integer/bool inputs,
fixed positive timesteps, radius 1, and Moore neighborhoods. Other inputs/rules
fall back to unmodified CellPyLib. It is not a general CellPyLib backend yet.

```python
import cellpylib as cpl
from examples.cellpylib_backend import evolve2d

initial = cpl.init_simple2d(60, 60)
history = evolve2d(initial, 60, cpl.game_of_life_rule)
# Same ndarray shape, dtype, full history and periodic boundaries as CellPyLib.
cpl.plot2d_animate(history)
```

The accelerated route uses the verified Life transition directly; arbitrary
Python callbacks are not compiled. Supplied historical prefixes are retained.
No upstream modification or global monkey patch is required. The dense Numba
ablation uses the same loop/transition as packed, with uint8 scratch buffers.
Packing reduces only the two scratch buffers, not the dense output history.

## Reproduction

Upstream: https://github.com/lantunes/cellpylib/tree/743e936d48f8520f6f4ac652570ac7bb46414189
(CellPyLib 2.4.0). The upstream repository is Apache-2.0; the regression test
reproduces its public Game of Life demo's glider/blinker/LWSS coordinates.

```sh
python -m pip install -e '.[test,numba]' \
  'cellpylib @ git+https://github.com/lantunes/cellpylib.git@743e936d48f8520f6f4ac652570ac7bb46414189'
python -m pytest -q tests/test_cellpylib_backend.py
python -m benchmarks.cellpylib_e2e --output docs/results/cellpylib.json
```

Benchmark scope includes deterministic uint8 input creation, validation,
encoding, all evolution, and full dense result history. Imports and rendering
are excluded. Each backend/size gets a fresh process; first call includes JIT,
then three warm calls are measured. Peak RSS is the process lifetime high-water
mark, including common imports, JIT, result hashing and all four calls; it is
not incremental array storage. All backends import the same modules. Warm
runs measure steady state, not a fresh-process application launch. Runs are
sequential in a fixed order, so these are exploratory measurements.

Every generation is compared by complete-history SHA256 across all five
backends. Tests also compare arrays directly, including the official demo,
small periodic grids, rectangular grids, history prefixes, dtype, and fallback.

## First measurements

macOS arm64, Python 3.12.8, NumPy 2.5.3, Numba 0.67.0.
128 x 128, 20 frames (initial frame plus 19 updates), seed 123:

| Backend | First call | Warm median | Peak RSS |
|---|---:|---:|---:|
| CellPyLib, memoize=False | 1.781 s | 1.790 s | 119.0 MiB |
| CellPyLib, memoize=True | 1.379 s | 1.252 s | 119.9 MiB |
| CellPyLib, recursive | 2.727 s | 2.671 s | 142.8 MiB |
| uint8 + Numba | 188.8 ms | 1.441 ms | 146.4 MiB |
| tightarray packed + Numba | 528.3 ms | 5.668 ms | 157.1 MiB |

Packed is approximately 221x faster warm than the fastest upstream option in
this random fixture, but 3.93x slower than dense Numba. Its first call is only
2.61x faster than that upstream option. At 64 x 64, packed's first call is
slower than upstream memoization (528 ms versus 320 ms). The result does not
establish a packing-specific speed or whole-process memory advantage.
The major gain is specializing the rule and removing Python per-cell work.

Next experiments should target word-parallel binary updates and larger grids.
A compact/lazy history API could save memory but would change CellPyLib's
ndarray return contract; it must be reported as a separate interface experiment.

Follow-up: [multi-state and large-grid sweep](cellpylib-multistate.md).
