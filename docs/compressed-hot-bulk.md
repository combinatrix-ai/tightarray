# Ordinary cached chunk bulk writes

The [benchmark](../benchmarks/compressed_hot_bulk.py) compares pinned `ae5c4ff`
Python with ordinary cached `_Hot.try_write` from `ef925f5`, measured at checkout
`4f2cb18`. Both use the same native extension. The
[raw artifact](compressed-hot-bulk-results.json) preserves all 162 configurations
and five shuffled paired repetitions unchanged. Every source/header/binary guard
passed. Later exact-bytes input-validation changes are not part of this run.

Five main layouts cover random direct 3/5/8-bit and high-label palette 3/5-bit
chunks. Periodic/span patterns are additional controls. Each ordinary chunk is
4096 bytes. Budgets 0/512/65536 exercise uncached, undersized and admitted hot
storage. Writes are 16/256/full4096 bytes at all budgets, plus 1/64 bytes at 65536.
Each trial makes 16 writes with every assigned value changed at that moment.
A shrinking-alphabet case makes one write, and a four-chunk round-robin pressure
case makes 32 writes under a 2048-byte budget. Inputs/traces and random order use
recorded seeds. Construction and correctness checks are excluded from timing;
scalar prewarm is identical and writes plus final flush are timed.

Eight smoke tests pass. Every measured output survives flush/clear/reload, every
sampled cache respects its payload budget, and adaptive cold-record SHA256 is
identical after flush between variants. Cold equality does not imply equal hot
capacity: the fast path may intentionally retain a wider hot representation.
Before/after/reloaded payload and retained graph are recorded; graph accounting
includes native references/metadata but excludes shared runtime, codec workspace,
transient buffers and allocator arenas. It is not RSS.

Dense ZSTD uses a decoded-byte LRU and one slice assignment per touched chunk,
not scalar emulation; codec level5/BITSHUFFLE/typesize1/one thread. Its helper
receives prevalidated fixture bytes and lacks the complete public write-validation
API, so comparisons are not fully symmetric API-overhead measurements. The
common budget constrains payload, not process memory.

## Admitted ordinary chunks

Milliseconds for 16 writes + flush with cache 65536. The raw artifact retains all
smaller-budget rows, controls, warm/cold sizes and all repetitions.

| Layout | Bytes/write | Codec | Baseline | Live | Dense ZSTD |
|---|---:|---|---:|---:|---:|
| direct-3bit | 1 | none | 0.084875 | 0.024416 | — |
| direct-3bit | 1 | zstd | 0.115292 | 0.058250 | 0.029834 |
| direct-3bit | 16 | none | 0.080500 | 0.025167 | — |
| direct-3bit | 16 | zstd | 0.115209 | 0.060542 | 0.030208 |
| direct-3bit | 64 | none | 0.085209 | 0.026291 | — |
| direct-3bit | 64 | zstd | 0.116792 | 0.060125 | 0.030875 |
| direct-3bit | 256 | none | 0.095750 | 0.036750 | — |
| direct-3bit | 256 | zstd | 0.124000 | 0.071958 | 0.032000 |
| direct-3bit | 4096 | none | 0.065000 | 0.070625 | — |
| direct-3bit | 4096 | zstd | 0.099709 | 0.098208 | 0.035709 |
| direct-5bit | 1 | none | 0.081084 | 0.024500 | — |
| direct-5bit | 1 | zstd | 0.117167 | 0.062125 | 0.031083 |
| direct-5bit | 16 | none | 0.083791 | 0.027917 | — |
| direct-5bit | 16 | zstd | 0.133292 | 0.064416 | 0.031708 |
| direct-5bit | 64 | none | 0.083375 | 0.027625 | — |
| direct-5bit | 64 | zstd | 0.139458 | 0.066125 | 0.033125 |
| direct-5bit | 256 | none | 0.084709 | 0.035375 | — |
| direct-5bit | 256 | zstd | 0.124000 | 0.074875 | 0.033208 |
| direct-5bit | 4096 | none | 0.063625 | 0.062833 | — |
| direct-5bit | 4096 | zstd | 0.102875 | 0.108792 | 0.037459 |
| direct-8bit | 1 | none | 0.068083 | 0.025875 | — |
| direct-8bit | 1 | zstd | 0.107750 | 0.065500 | 0.032250 |
| direct-8bit | 16 | none | 0.068917 | 0.025375 | — |
| direct-8bit | 16 | zstd | 0.117083 | 0.072333 | 0.035834 |
| direct-8bit | 64 | none | 0.068166 | 0.027666 | — |
| direct-8bit | 64 | zstd | 0.113292 | 0.068667 | 0.032333 |
| direct-8bit | 256 | none | 0.069541 | 0.037000 | — |
| direct-8bit | 256 | zstd | 0.114542 | 0.078667 | 0.033417 |
| direct-8bit | 4096 | none | 0.062500 | 0.061583 | — |
| direct-8bit | 4096 | zstd | 0.100500 | 0.097334 | 0.036459 |
| palette-3bit | 1 | none | 0.136750 | 0.027708 | — |
| palette-3bit | 1 | zstd | 0.248167 | 0.135917 | 0.029084 |
| palette-3bit | 16 | none | 0.135500 | 0.027792 | — |
| palette-3bit | 16 | zstd | 0.250333 | 0.143250 | 0.030416 |
| palette-3bit | 64 | none | 0.134334 | 0.029375 | — |
| palette-3bit | 64 | zstd | 0.255625 | 0.163417 | 0.036541 |
| palette-3bit | 256 | none | 0.135875 | 0.038083 | — |
| palette-3bit | 256 | zstd | 0.253667 | 0.151791 | 0.030750 |
| palette-3bit | 4096 | none | 0.097750 | 0.100542 | — |
| palette-3bit | 4096 | zstd | 0.214625 | 0.212541 | 0.034250 |
| palette-5bit | 1 | none | 0.144417 | 0.029709 | — |
| palette-5bit | 1 | zstd | 0.228875 | 0.125709 | 0.040917 |
| palette-5bit | 16 | none | 0.144125 | 0.030750 | — |
| palette-5bit | 16 | zstd | 0.213042 | 0.098125 | 0.031833 |
| palette-5bit | 64 | none | 0.152125 | 0.033917 | — |
| palette-5bit | 64 | zstd | 0.239792 | 0.111250 | 0.032583 |
| palette-5bit | 256 | none | 0.148542 | 0.042167 | — |
| palette-5bit | 256 | zstd | 0.216792 | 0.103459 | 0.034041 |
| palette-5bit | 4096 | none | 0.106000 | 0.106541 | — |
| palette-5bit | 4096 | zstd | 0.187958 | 0.184584 | 0.039000 |

Partial 16-byte writes improve 2.72–4.88× without a codec and 1.62–2.17× with ZSTD.
At 256 bytes the improvements are 1.88–3.57× and 1.46–2.10×. Full-chunk writes use
the existing replacement path and remain approximately unchanged: median live/
baseline ratio 0.989, range 0.968–1.087. Dense cached ZSTD still wins: 16-byte writes
take 0.030–0.036 ms versus live 0.061–0.143 ms. Packing and multi-candidate cold
encoding retain real costs even after avoiding repeated full hot decoding.

For main layouts that cannot retain a hot chunk, controls are near unchanged:
cache 0 median live/base 1.005 (range 0.931–1.109), cache 512 median 1.003
(range 0.941–1.092). Those ranges include sampled regressions; no universal
no-regression claim follows. At large cache, periodic/span controls can become
ordinary hot chunks after edits, so they also benefit: 16-byte none periodic
0.08687→0.03121 ms and span 0.07992→0.02917 ms. They are not expected to be wholly
unaffected paths after their first structural expansion.

## Retained hot width after alphabet shrink

The fixture initially has random 0/1 values and a single 7. Replacing that 7 with 0
lets canonical cold encoding shrink to 512 bytes. At large cache:

| Codec | Initial hot | Baseline hot after flush | Live hot after flush | Hot after clear/reload, both | Baseline/live owned after flush |
|---|---:|---:|---:|---:|---:|
| none | 1027 | 512 | 1027 | 512 | 2745 / 3260 |
| zstd | 1536 | 512 | 1536 | 512 | 2729 / 3753 |

Live none retains 515 more owned bytes; live ZSTD retains 1024 more. Cold records
are identical, cache budgets remain respected, and eviction/clear releases the
wider hot representation. Avoiding repacking is therefore a hot-memory tradeoff,
not a free size-preserving speed optimization. With budget 512 the old hot entry
cannot be admitted, and both implementations end with 512-byte hot data.

The four-chunk eviction-pressure case keeps only one 1536-byte hot chunk in its
2048-byte budget. None writes improve 0.41175→0.32363 ms, while ZSTD
1.52908→1.49887 ms changes little; storage/cache sizes remain equal. Frequent
misses and codec work limit the benefit. These are bounded synthetic traces,
not whole-application throughput measurements.

```sh
python -m benchmarks.compressed_hot_bulk --output /tmp/hot-bulk.json
python -m pytest -q tests/test_compressed_hot_bulk_benchmark.py
```
