# Actual immuneML continuous k-mer integration

This experiment changes the dispatch inside immuneML's real repertoire encoder,
then runs its train-vocabulary fit, test transformation, relative-frequency
normalization, variance scaling, and LogisticRegression fit/predict. It is not
just a k-mer primitive benchmark. The default BioNumPy dispatch remains intact;
tightarray is an explicit per-encoder opt-in.

## Result

On 100 example repertoires containing 2,806 sequences, the opt-in path reduced
median full encoding/classifier pipeline time from **41.36s to 14.26s (2.90×)**.
Including input loading and Repertoire preparation, the median was **55.96s to
28.97s (1.93×; 48.2% less elapsed time)**. Three fresh workers per backend were
measured. These are ratios of medians, not sums of independently median phases.

| Phase | Upstream BioNumPy | tightarray adapter |
|---|---:|---:|
| Input/Repertoire preparation | 13.760s | 14.715s |
| Training repertoire encoding, normalization and scaling | 32.004s | 10.360s |
| Held-out repertoire transformation | 8.986s | 3.789s |
| Classifier fit | 3.52ms | 3.43ms |
| Prediction + probabilities | 0.35ms | 0.30ms |
| Pipeline | 41.363s | 14.259s |
| Preparation + pipeline | 55.963s | 28.974s |

All six workers produced bit-identical train/test CSR matrices (80×7,761 and
20×7,761), features, labels, example IDs, coefficients/intercept, predictions and
probabilities. Every worker predicted **both classes**, so this was not a
constant-prediction classifier check. Training CSR storage was the same
333,372 bytes for both backends. No accuracy or clinical benefit is claimed.

The [unchanged raw artifact](bio-immuneml-pipeline-results.json.gz) contains
all timings and identities. All 662 source/data guards matched within each
worker, between all six workers, and in a final live-source check. The measured
script is preserved byte-for-byte; use the explicit `--ks 3` command below.
Ten integration tests passed in the source-level immuneML environment; package
strict mypy validation also passed. The tiny classifier timings are included for
pipeline completeness, not evidence of classifier speedup.

## Integration and supported scope

The portable patch is
[`immuneml-continuous-aa.patch`](../benchmarks/bio/patches/immuneml-continuous-aa.patch),
for [immuneML commit 24d74abb](https://github.com/uio-bmi/immuneML/tree/24d74abb2d30b081f9d6359a688a3e827c983e44).
Apply it to that source checkout, make the companion package importable, and use:

```python
from tightarray_immune.immuneml_integration import configure_encoder

configure_encoder(encoder, backend="tightarray")
encoded = encoder.encode(dataset, encoder_params)
# Return this instance to upstream behavior:
configure_encoder(encoder, backend="bionumpy")
```

Only continuous amino-acid k-mers without gene/locus prefixes are supported by
the opt-in path. Gapped and IMGT-specific encoding strategies, nucleotide
sequences, and prefix requests raise explicitly. Region extraction remains
upstream; the experiment uses its IMGT_CDR3 region selection. Inactive gap
parameters are ignored exactly as upstream continuous dispatch does, including
its normal `k_left=1, k_right=1` defaults. Original sequence row IDs preserve
read weighting. Tests cover actual weighted encoding, short/empty sequences,
unsupported modes, deepcopy, and the encoder's backend-sensitive cache key.

There is a dependency limitation: this immuneML pin declares NumPy <=1.26.4 and
SciPy <=1.12, while tightarray-immune requires NumPy >=2. The measured environment
uses source imports with NumPy 2.5.3, SciPy 1.18.1, BioNumPy 1.0.14 and
scikit-learn 1.9.1. This is a tested source-level experiment, **not a supported
pip co-install**. Full immuneML installation and its complete test suite were
not validated.

## Workload and measurement boundaries

The public DeepRC example dataset supplies 100 repertoires and its original
`binary_target_1` labels. The split is stratified 80/20 with seed 42. These are
supplied example labels, not clinical validation. Input conversion assumes one
TRB locus, uses the provided amino-acid sequences and template counts, and the
measured encoder uses Reads.UNIQUE. No sequences are synthesized or duplicated.
Each worker imports real immuneML, creates fresh Repertoire files and cold
upstream caches, and uses one upstream Pool worker. BLAS/OpenMP thread limits
are one. Train and test matrices remain upstream CSR arrays.

For k=3, three fresh processes per backend run in a seeded, rotated order.
`pipeline` includes encoding through prediction; `prepare_plus_pipeline` also
includes TSV loading, Repertoire conversion/writes and splitting. Python process
startup/imports, source hashing, and output serialization are outside these
intervals. No nested cross-validation or hyperparameter search is performed.
The report's exactness checks compare CSR values/indices/indptr, feature names,
example IDs, labels, classifier coefficients/intercept, probabilities and
predictions across every backend/repeat.

The gain must not be attributed to the new packed bulk-write SIMD kernel.
This integration emits only observed k-mer labels, avoiding BioNumPy's complete
alphabet-to-the-power-k label table. It still pays for converting upstream ragged
arrays into sequences. Equal final CSR matrices imply no feature-matrix memory
reduction; RSS was not measured.

## Reproduction and provenance

The benchmark is [`immuneml_pipeline.py`](../benchmarks/bio/immuneml_pipeline.py).
Use a disposable source checkout/environment as described above, then:

```sh
PYTHONPATH=/path/to/patched/immuneML:/path/to/tightarray:/path/to/tightarray/packages/tightarray-immune/src \
  python -m benchmarks.bio.immuneml_pipeline \
  --upstream /path/to/patched/immuneML --data /path/to/DeepRC/example_dataset \
  --ks 3 --repeats 3 --output results.json.gz

python -m pytest packages/tightarray-immune/tests/test_immuneml_integration.py
```

The local reference was a sparse partial clone with missing promisor objects;
normal cloning failed. The writable experiment therefore copied the available
tracked source files into an isolated snapshot, with upstream push disabled.
Two missing documentation-import helpers under `scripts/` were fetched from the
same public commit. The snapshot's local Git identity is not claimed to be the
upstream commit. The raw artifact records the upstream pin and SHA-256 hashes
of all measured Python/native sources, the loaded extension, patch and dataset;
each worker checks these before and after execution. The AGPL upstream source
is not vendored into this repository; only the small integration patch is kept.

An earlier mixed k=3/k=4 run was stopped when its first k=4 BioNumPy worker
exceeded five minutes. Its controller did not checkpoint prior worker outputs,
so those earlier k=3 timings are not used as the primary result. The harness now
atomically saves each complete worker, and the primary k=3 experiment was
repeated from scratch. No k=4 speed ratio is claimed from that partial run.
