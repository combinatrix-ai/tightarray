# Modal trimmed-span prototype

This benchmark-only candidate omits a chunk's leading and trailing modal value,
retaining an eight-byte descriptor, optional palette, and packed interior. It
selects the candidate only when its exact encoded byte length beats the existing
candidate. The production implementation is unchanged. Guards reject impossible
wins before allocating a packed candidate; finding the modal value still incurs
a NumPy histogram scan.

The [script](../benchmarks/compressed_trimmed_policy.py) uses the Python baseline
from commit `eff5443` (SHA256
`34f980dad4d98a64c7e8a9cfa1931ece42562c6f5203b34c8ea39ae808932c6b`)
and the current native extension recorded in the
[unchanged measured artifact](compressed-trimmed-policy-results.json). This is
not a historical full build of that commit. Source hashes, including the script
and native binary, matched before and after measurement. The guarded live Python
file is recorded for provenance but baseline classes execute the pinned source.

Each case contains 1 MiB of logical bytes, in 4096-byte chunks, with a 64 KiB
hot cache budget. Three paired repetitions randomize the order of six methods.
Dataset seeds are 723 (explicit patterns) and the shared harness's 812 (rare and
uniform fixtures); method order uses 724 and access traces use 914. Each access
phase performs 256 scalar reads; updates perform 64 assignments plus flush.
Local reads prewarm eight chunks. Global reads begin with an empty cache. Dense
Blosc2 baselines use level 5, BITSHUFFLE, typesize 1 and one thread. The shared
harness verifies all results and post-update contents outside measured phases.
Eight additional tests cover exact decoding, structural boundaries, partial last
chunks, cache zero, slices, scalar mutation, and bulk writes.

Cold retained bytes below use the same deduplicated reachable-object walk for
all methods, including prototype instance/slot fields and native Array buffers.
They include Python graph overhead and cold records; they are neither packed
payload sizes nor RSS. Shared modules and codec runtime state are excluded;
allocator arenas, transient buffers, and native codec workspaces are not measured.

| Case | Baseline none | Trim none | Baseline ZSTD | Trim ZSTD | Dense LZ4 | Dense ZSTD |
|---|---:|---:|---:|---:|---:|---:|
| Random half, zero half | 667781 | 341637 | 355436 | 341613 | 363623 | 358748 |
| Zero half, random half | 667733 | 341589 | 355389 | 341565 | 361046 | 360490 |
| Central random island | 521773 | 177701 | 192785 | 177677 | 202227 | 196350 |
| Random 32 labels | 667653 | 667653 | 667637 | 667637 | 686555 | 682715 |
| Half with edge outlier | 667653 | 667653 | 355572 | 355572 | 366302 | 362389 |
| Rare spikes | 19140 | 19140 | 19124 | 19124 | 47234 | 38209 |
| Uniform chunks | 7813 | 7813 | 7797 | 7797 | 32204 | 29694 |

For the first three cases, ZSTD baseline → trimmed medians in milliseconds:

| Case | Construction | Local scalar reads | Global scalar reads | Updates + flush |
|---|---:|---:|---:|---:|
| Random half, zero half | 13.889 → 19.230 | 0.083 → 0.118 | 1.190 → 0.803 | 3.958 → 4.732 |
| Zero half, random half | 13.501 → 19.244 | 0.083 → 0.113 | 1.381 → 0.669 | 3.215 → 4.739 |
| Central random island | 12.239 → 20.127 | 0.084 → 0.109 | 1.143 → 0.472 | 3.123 → 6.746 |

The candidate saves 48.8% of retained graph bytes against uncompressed packing
on the half-random case, but only 3.9% against existing ZSTD. The central island
saves 65.9% and 7.8%, respectively. It improves global reads for these cases,
while Python recognition, Python hot access, and expansion on first mutation
make construction, local reads and updates slower. Uncompressed half-case
construction is 2.024 → 7.863 ms and updates are 0.596 → 1.903 ms.

No-trim random data, an edge outlier, and rare spikes retain the exact baseline
size while paying recognition overhead: none construction is respectively
2.017 → 5.546, 1.875 → 5.124, and 1.337 → 6.162 ms. Uniform cold chunks bypass
the candidate and preserve construction time, but later updates can create
nonuniform chunks and incur the extra scan. The edge outlier demonstrates how
fragile the contiguous-span opportunity is; existing sparse/RLE formats already
win on rare spikes. These seven synthetic cases establish a bounded structural
opportunity, not a general application win or a guarantee about native speed.
Native recognition and hot access need separate measurement before default
adoption; compressed trimmed interiors were not evaluated.

Reproduce from a checkout containing the pinned commit and a built extension:

```sh
python -m benchmarks.compressed_trimmed_policy --output /tmp/trimmed-results.json
pytest -q tests/test_compressed_trimmed_policy.py
```
