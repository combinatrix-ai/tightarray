# Non-biological application reconnaissance

Reviewed primary source code/docs on 2026-09-21. These are ranked integration
hypotheses, not measured speed or capacity claims. MiniGrid is handled by a
separate pilot; Quarry is already an established earlier experiment and is not
repeated here. Pin a commit before implementation because source links track
branches.

## 1. gym-sokoban: visited-state keys in real puzzle generation

The level generator creates NumPy native-integer rooms containing tile IDs 0–5.
Its actual reverse-play DFS stores `marshal.dumps(room_state)` keys in a set,
stops at 300,000 visited states, and copies the active board per child. This is
already a many-state workload, without inventing a replay buffer.
[Generator source](https://raw.githubusercontent.com/mpSchrader/gym-sokoban/default/gym_sokoban/envs/room_utils.py)

**Seam:** change only visited-key encoding first. Keep active-board operations
unchanged. Compare current marshal keys, contiguous uint8 bytes, tightarray 3bit
bytes, and a domain-specific player/box-position key. Fixed geometry/shape must
be part of the key domain; preserve exact state identity and deterministic
search traversal. Set/object overhead remains and can dominate small boards.

**Experiment:** run the actual generator with matched seeds, action order and
node cap; compare explored-state count, chosen board/score, total time and peak
RSS. Then compare completed exploration under the same process-memory budget.
Reject a claimed tightarray win if uint8 or a sparse domain key achieves it
more cheaply. Single interactive board storage is too small to matter.

## 2. GDPC: read-mostly Minecraft world slices

`WorldSlice` retains parsed NBT, palettes and per-section `_BitArray` objects.
Each access performs Python integer division/shifts into existing word-aligned
packed data. Block width is `max(4, ceil(log2(palette_size)))`; biome width is
at least 1. There is an exact backend seam at `_BitArray.__getitem__`.
[WorldSlice source](https://raw.githubusercontent.com/avdstaaij/gdpc/master/src/gdpc/world_slice.py)

**Experiment:** load a saved public/generated chunk response without a live
server; compare identical block/biome lookup traces, terrain classification,
constructor plus full operation time, and RSS. Preserve bit order and palettes.
Tightarray's current 1–8bit limit excludes large palettes and some heightmaps;
explicitly constrain the pilot or expand the core deliberately.

**Caution:** storage is already packed. Repacking while retaining `_nbt` adds
a second copy. Capacity requires ownership changes, not just replacing the
lookup method. Block-object construction and coordinate conversion may dominate
E2E even if raw indexing improves. This is mainly an access-speed candidate.

## 3. Crafter: terrain material plane and semantic snapshots

`World` holds a uint8 material map and uint32 object-index map. Its material
API includes scalar updates, regional `nearby`/`mask`, and global `count`.
`SemanticView` copies the material map and overlays object classes.
[Engine source](https://raw.githubusercontent.com/danijar/crafter/main/crafter/engine.py)
The standard material list has 12 entries, plus the engine's zero sentinel,
so 4bits suffice for this terrain plane; semantic IDs require their own bound.
[Material definitions](https://raw.githubusercontent.com/danijar/crafter/main/crafter/data.yaml)

**Experiment:** wrap just `_mat_map`, unpack only requested regions, and run
real reset/step/render traces with seeded worlds. Compare all observations,
rewards and state transitions. Measure enlarged worlds or many resident worlds;
report default-size behavior separately.

**Caution:** two-dimensional slicing, equality masks, copies and renderer output
prevent a direct array substitution. The untouched uint32 object plane costs
four times the material plane; halving terrain alone saves only 10% of those
two planes combined, before other objects. Terrain-only snapshots may be a
better target than live environment capacity.

## 4. Mesa: categorical property layers, conditional candidate

Mesa documents NumPy-backed property layers, including configurable dtype,
while its discrete grid retains cell objects and their neighbor connections.
[Discrete-space API](https://mesa.readthedocs.io/latest/apis/discrete_space.html),
[Architecture overview](https://mesa.readthedocs.io/stable/overview.html)

**Seam:** an explicitly categorical property layer (e.g. terrain/fire stage),
not arbitrary float-valued layers or agent IDs. State cardinality is
model-dependent: choose an existing model with at most 256 actual values, rather
than pretending Mesa generally has a small alphabet.

**Experiment:** identify and pin one real model, measure its layer/agent/cell
memory breakdown, then replace only that layer and compare seeded full runs.
Broadcast assignment, masks, NumPy operations and exposed ndarray contracts
require an adapter. Reject if cell/agent objects dominate RSS, or if every
step immediately materializes the entire layer. This has lower priority until
a concrete model's memory profile proves the layer matters.

## Rejected as a direct replacement: AgentPy generic Grid

The stable 0.1.5 source allocates an object field containing an `AgentSet` for
every cell, a list of all coordinates, and optional empty-cell bookkeeping.
This represents arbitrary agent identities and multiplicity, not a small
categorical state alphabet. Its added fields live inside a NumPy structured
record array.
[Grid implementation](https://agentpy.readthedocs.io/en/stable/_modules/agentpy/grid.html)

Packing a boolean occupancy field leaves the dominant object structure intact.
Removing those objects would be a new grid architecture with changed API
semantics. Consider only a separately profiled categorical auxiliary field;
do not sell generic AgentPy grid capacity as a low-effort tightarray win.

## Decision

Start with Sokoban's existing visited-state set: the application already keeps
many categorical states, and the seam is narrow. GDPC is the next best access
candidate. Crafter and Mesa require profiling to show the compressed plane
matters to total application memory. All capacity comparisons must include
simple uint8, domain-specific representations, Python container overhead and,
where relevant, chunk compression rather than comparing only to default int64.

The subsequent [real Sokoban pilot](real-sokoban-search.md) measured a concrete
tradeoff: about 25% less retained-key-set memory than uint8 for about 12% more
search time in the 5,000-state case; sparse keys remain smaller.
