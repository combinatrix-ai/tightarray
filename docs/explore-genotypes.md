# Genotype storage and query exploration

This pilot uses the real scikit-allel 1.3.13 `GenotypeArray.to_packed`,
`from_packed`, and `count_alleles` APIs on synthetic diploid biallelic calls.
Both ordered allele slots, including partially missing calls, survive exactly.
No separate phasing-status mask or external sample/variant metadata is included.
Allele order is preserved, which is necessary but is not a claim that the pilot
stores all metadata of phased VCF records.

The input shape is `(8192 variants, 1024 samples, 2 alleles)`, with int8 values
-1 (missing), 0 (reference), and 1 (alternate). Common variants draw per-variant
alternate frequencies from 5–50%; rare variants draw from 0.01–1%; both include
1% independently missing alleles. This is synthetic independent variation,
not real linkage disequilibrium or an application-level genetic analysis.

## Comparators

- NumPy int8, 2 bytes per diploid call.
- scikit-allel `to_packed`, 1 byte per call. This existing format supports
  diploid calls with up to 15 alleles; its extra generality costs space here.
- tightarray, offset encoding `allele + 1`, 2 bits per allele / 4 bits per call.
  The pilot explicitly rejects non-biallelic inputs.
- Blosc2 4.13.1, ZSTD level5 + BITSHUFFLE, typesize1, one compression and
  decompression thread, independent chunks of128 variants. Payload includes
  each compressed chunk's header; Python object overhead is excluded.

The standard query extracts a region, invokes the same scikit-allel
`count_alleles(max_allele=1)`, and computes missing-allele counts. A separate
Numba-fused query performs all three counts directly from tightarray storage,
with an equivalent uint8-width int8 dense Numba ablation. This separates any
packing benefit from removing intermediate allocations and library overhead.

All32 sampled regions preserve every allele exactly; all query outputs and
full-scan counts are checked against dense scikit-allel. Full scans use128-variant
chunks, and sampled requests each use64 contiguous variants across all samples.
Median times use3 repeats, with construction reported separately. Numba first
small-call compile times are reported separately; steady-state numbers must not
be treated as cold-start performance. Process RSS is not measured here: resident
payload and throughput are screening metrics, not demonstrated process capacity.
Input generation and output persistence are outside query timing. Decoding and
count output allocation are inside it. Building starts from a dense input.

Run:

```sh
python -m benchmarks.explore_genotypes --output docs/results/explore-genotypes.json
pytest -q tests/test_explore_genotypes.py
```

Results are in [machine-readable results](results/explore-genotypes.json).

## Observed results

macOS arm64, Python3.12.8, NumPy2.5.3. Values below are warm medians;
all12 distribution/backend/query combinations passed exact checks.

| Distribution | Backend | Payload MiB |32 sampled-region queries ms | Full scan ms |
|---|---|---:|---:|---:|
| Common | NumPy + scikit-allel |16.00 |9.87 |39.08 |
| Common | Existing scikit-allel packing |8.00 |11.30 |44.60 |
| Common | tightarray + scikit-allel |4.00 |10.86 |42.53 |
| Common | Blosc2 + scikit-allel |2.01 |20.19 |55.96 |
| Rare | NumPy + scikit-allel |16.00 |10.48 |41.43 |
| Rare | Existing scikit-allel packing |8.00 |11.86 |46.43 |
| Rare | tightarray + scikit-allel |4.00 |11.49 |44.10 |
| Rare | Blosc2 + scikit-allel |0.482 |20.18 |54.10 |

Tightarray takes half the payload of scikit-allel's existing packed diploid
format and retains similar query performance. Its observed4–5% full-scan
advantage over that format is small and should not be promoted to a robust
speedup without repeated independent runs. Both are slower than dense NumPy.

Blosc2 uses about half of tightarray's payload on common variation, and about
one eighth on rare variation. Tightarray therefore does not win maximum
capacity against this comparator. It offers an intermediate storage/query
tradeoff: sampled queries are about1.8 times faster than this Blosc2 path,
while taking2.0 or8.3 times its storage. Chunk geometry affects this tradeoff.

Fused Numba full scans take34.36/36.49ms for tightarray versus34.90/36.75ms
for dense arrays (common/rare), effectively parity at this exploratory scale.
This is encouraging for resident packed analysis but is not evidence of a
packing-driven speedup. Fused dense is essential to that interpretation.

Construction takes3.4–4.4ms for tightarray,5.6–6.5ms for existing allele
packing,0.9–1.2ms for dense copying, and81–91ms for Blosc2. These are single
construction timings, not repeated medians, and exclude synthetic generation.
The single small-call JIT timings in JSON should be added when considering
first-use costs. No process-memory-limit or real-data E2E claim is made.

## Follow-up value

A worthwhile candidate is repeated region analysis of resident biallelic data
where RAM is constrained but compressed chunk decode latency matters. Before
an integration decision, use real public phased data, preserve required phase
and variant metadata, test several chunk shapes and compression settings,
and compare an actual analysis pipeline. For read-mostly rare variants, the
stronger capacity result belongs to Blosc2 in this pilot.
