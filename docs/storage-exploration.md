# Where narrow packed storage is useful

Four bounded pilots compare actual storage/access paths, not full training,
clinical, or production pipelines. None establishes application-wide speedup
or maximum RAM capacity: these tests report stored payload, not peak RSS.
For an actual fixed-RSS capacity experiment see [the CA study](capacity-grid.md).

## Findings

| Candidate | Concrete measured benefit | Boundary |
|---|---|---|
| Discrete replay observations | Uniform 8-state records: 37.5% of uint8 payload; sampled batches 0.099ms versus BITSHUFFLE ZSTD 0.302ms, with slightly less storage | NumPy is faster; spatially structured observations favor ZSTD capacity by a large margin; not SB3 training |
| Small 3D label patches | Uniform 256³, 16 patches of 4³: packed6MiB / 10.75us versus Blosc LZ4 6.81MiB / 261.79us | Dense+Numba is 5.21us; absolute saving only~0.25ms; structured semantic masks and larger patches favor compression |
| Biallelic diploid genotypes | 4MiB versus scikit-allel packing8MiB with similar query time, preserving ordered allele calls and missingness | Specialized biallelic representation; Blosc2 common2.01MiB / rare0.482MiB wins storage; source is synthetic |
| Online category edits | Uniform 8-state field:6MiB versus uint8 16MiB; immediate scalar edits avoid compressed-region rewrite overhead | Deferred/batched edits and dirty-chunk caches could narrow the difference; compiled dense is faster |

The repeatable niche is **small alphabets with weak spatial compressibility,
plus fine-grained access or immediate mutation**. The strongest counterexample
is a spatially coherent or highly skewed field, where fixed bit width leaves
substantial entropy compression available. Blosc BITSHUFFLE was explicitly
included, so unused bit planes were not withheld from the comparator.

Existing application-specific bit packing is another relevant baseline.
The genotype pilot does not claim a universal compression novelty: it trades
scikit-allel's support for up to15 alleles for a narrower biallelic format.

## What to pursue

1. A mutable categorical field / sparse-query storage adapter is the clearest
   capability fit. Validate real edit locality and batching requirements before
   generalizing the scalar benchmark's large ratio.
2. A real discrete replay trace is an accessible integration target. Retain
   the encoded buffer at realistic scale, include ring replacement and sampled
   transition materialization, measure actual data-loader/training time and RSS.
   Uniform synthetic boards are a favorable case, not evidence that actual
   environment traces have that entropy.
3. A scikit-allel biallelic adapter is a concrete capacity/throughput compromise;
   first validate public real variants and compare chunk compression. The
   current small timing advantage against existing packing is not decisive.
4. Do not prioritize a blanket replacement of compressed segmentation masks:
   coherent masks strongly favor general compression in this exploration.

## Reproduction and methodology

- [Replay methods and samples](explore-replay.md)
- [3D patches and dense-Numba ablation](explore-labels.md)
- [Real scikit-allel query functions on synthetic genotypes](explore-genotypes.md)
- [Online mutation contract](explore-edits.md)

All use Python3.12.8, NumPy2.5.3, Blosc2 4.13.1, with Numba0.67.0 where needed;
scikit-allel is1.3.13. Benchmarks were scheduled sequentially across agents to
avoid intentional simultaneous CPU measurement. Compression settings, layouts,
cache reuse, JIT exclusions and limitations are recorded per pilot. Different
workloads have different timings and batching; cross-row ratios are invalid.
No upstream application was modified or published. Core tightarray is unchanged.

```sh
python -m pip install -e '.[test,numba]' blosc2==4.13.1 scikit-allel==1.3.13
python -m pytest -q tests/test_explore_*.py
python -m benchmarks.explore_replay
python -m benchmarks.explore_labels
python -m benchmarks.explore_genotypes
python -m benchmarks.explore_edits
```
