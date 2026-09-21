# Non-bio application experiments

Follow-up to [synthetic storage exploration](storage-exploration.md), using
actual application code, environment transitions and shipped assets.
These measurements do not establish an overall process RSS capacity frontier.

## Best concrete seam: puzzle-search visited keys

The actual pinned gym-sokoban reverse-search code was run with one key encoder
replacement and the same 5,000-state cap for all variants. Active dense boards,
action order and search logic were unchanged. All visited counts, key calls,
scores, resulting boards and box mappings matched for three seeds. Two seeds
exhausted small, nonproductive searches; seed37 reached the cap with score1440.

Seed37, 10x10 board, median of three searches:

| Key representation | Retained set + key objects | Search time |
|---|---:|---:|
| Original marshal | 4.715 MB | 204 ms |
| uint8 bytes | 1.190 MB | 197 ms |
| tightarray 3bit word bytes | 0.890 MB | 221 ms |
| Sparse changes against fixed board | 0.765 MB | 321 ms |

Against the simple uint8 alternative, packing saves25% of retained key-set
memory for12% more search time. Against the original keys it saves81%, but
much of that is already achieved by uint8. A domain-specific sparse key uses
less memory still; this particular NumPy/Python sparse implementation is slower.
A more optimized sparse encoder might move that frontier. These are owned
Python set/key sizes, not total RSS; recursion, active boards and runtime are
excluded. The pinned upstream normal cap is300,000, not tested here.
[Full source pin, methods and results](real-sokoban-search.md).

This is the strongest next scale test: a real application already retains many
categorical states, with a narrow integration seam. Next measure fresh-process
RSS and completed states under an identical memory budget, rather than
extrapolating set bytes into application capacity.

## Replay from actual MiniGrid transitions

Three environments, 2,048 transitions each, retain pre/post symbolic images,
actions, float64 rewards, termination/truncation, episode IDs, directions and
mission references. Episode resets do not replace final observations.

- Packed image payload is50% of uint8; batch64 transition sampling~0.060ms.
- Single-transition BITSHUFFLE ZSTD is42–44%, sampling~0.16ms.
- 32-transition ZSTD chunks are6–8%, sampling~0.72–0.75ms.
- NumPy is~0.006–0.007ms but retains full dense image payload.

The synthetic best-capacity result does not survive these redundant real
traces. Packed remains a capacity/latency compromise. Its decode advantage
survives a single-transition comparator without unrelated-transition decode,
but this is buffer sampling, not training E2E or a RAM-sized buffer test.
[Detailed results](real-minigrid-replay.md).

## MiniGrid live-world seam: lower priority

Grid encode/store/materialize/decode works with packed 4/3/2-bit channels,
but the small structured grids favor general compression. DoorKey16x16:
NumPy768B, packed288B, ZSTD135B payload. Full pipeline for20 grids:
5.766/6.034/6.610ms respectively. Object mutation/identity and Box.contains
prevent these snapshots from replacing live Grid or complete checkpoints.
[Methods and limitations](real-minigrid-grid.md).

## Game sprites: mostly rejected

Seven of ten unmodified pygame-ce assets require8-bit palette indices, so
narrow packing offers no additional index-plane reduction. The low-color
assets have structure that encoded images exploit. No lossy quantization was
used to manufacture a narrow alphabet. This is an eligibility audit, not an
engine performance benchmark. [Asset audit](real-sprite-audit.md).

## Other targets examined

[Source-level reconnaissance](nonbio-targets.md) ranks GDPC's existing packed
word access, Crafter's terrain plane, and Mesa categorical property layers.
GDPC is mainly an access-speed candidate; Crafter's uint32 object plane limits
terrain-only capacity gains; generic AgentPy grids are dominated by objects
rather than small categorical arrays. These are inspected hypotheses, not
measured integrations.
