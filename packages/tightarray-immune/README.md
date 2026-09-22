# tightarray-immune (experimental)

An independently installable adapter package in the tightarray repository. The
core library knows only numeric arrays; this package owns amino-acid alphabets,
sequence boundaries, feature ordering and application output contracts. Importing
it does not patch any installed application. It is not yet published to PyPI.

From the repository root:

```sh
pip install -e .
pip install -e './packages/tightarray-immune[scirpy]'
```

NumPy and the matching development version of tightarray are the base dependencies.
SciPy is optional unless importing the Scirpy adapter. immuneML, DeepRC, MotifBoost,
Scirpy itself, Torch and their training stacks are not runtime dependencies.
This package currently uses tightarray's private experimental sequence kernels;
install both packages from the same checkout.

```python
from tightarray_immune import SequenceBatch
from tightarray_immune import deeprc, immuneml, motifboost, scirpy

sequences = ["CASSL", "CASSF", "CAS"]
batch = SequenceBatch(sequences)

# MotifBoost's default weighted, normalized trigram feature order.
features = motifboost.ngram_features(sequences, weights=[5, 2, 1])
# Reuse encoded storage across repeated feature extraction:
repertoire = motifboost.MotifRepertoire(sequences)
features_again = repertoire.features([5, 2, 1])

# Feed labels and mapped repertoire IDs into immuneML's vectorizer.
labels, sequence_ids = immuneml.continuous_kmers(batch, k=3)

# Explicit selection: duplicate indices and order are preserved.
# Counts/scaling and torch conversion remain with the dataset/collate function.
codes, lengths = deeprc.padded_batch(batch, [0, 2])

# CSR: a stored 1 means zero mismatches; absent edges exceed the cutoff
# or compare sequences of unequal length.
distances = scirpy.hamming_distance(batch, cutoff=2)
```

## Explicit application integration

The experimental bridges target the source revisions and environments recorded in
[MotifBoost pipeline validation](../../docs/bio-motifboost-pipeline.md) and
[immuneML pipeline validation](../../docs/bio-immuneml-pipeline.md). They do not
change upstream installations merely by being imported.

For MotifBoost, wrap actual classifier construction, fitting and prediction:

```python
from motifboost.methods.motif import MotifBoostClassifier
from tightarray_immune.motifboost_integration import motifboost_backend

with motifboost_backend("tightarray"):
    model = MotifBoostClassifier(
        n_jobs=1, classifier_method="linear_regression",
        augmentation_times=0, tfidf_mode=False
    )
    model.fit(train_repertoires, train_labels)
    probabilities = model.predict_proba(test_repertoires)
```

This temporarily selects the feature function used by upstream fork workers;
TF-IDF, feature caching and the classifier remain upstream. The context restores
the previous function on exit, including failure. Nested or concurrent selection
is unsupported. Use single-character ASCII symbols, a distinct boundary absent
from sequences, and at most 1,000,000 total features across the requested k-mer
blocks.
Weights must be nonnegative integers whose totals remain exactly representable.
The application must support its upstream `fork` multiprocessing path.

On the 100-repertoire example fixture, actual load/fit/predict with upstream
logistic regression and TF-IDF disabled measured 194.2 ms versus 136.2 ms
(three fresh-process repetitions). Features and predictions matched; peak RSS
was essentially unchanged. This small-fixture result is separate from the much
larger feature-only speedups below. See the pipeline report for timing variance,
preparation costs and upstream LightGBM/TF-IDF limitations.

For immuneML, apply the source-pinned
[encoder patch](../../benchmarks/bio/patches/immuneml-continuous-aa.patch) to a local
checkout first, then select a backend on the encoder instance:

```python
from tightarray_immune.immuneml_integration import configure_encoder

configure_encoder(encoder, backend="tightarray")
# Continue with immuneML's normal encoder/vectorizer/classifier calls.
```

Only continuous amino-acid k-mers without gene/locus prefixes are supported.
Gapped encoding modes are rejected. The original BioNumPy path remains the
default. The pinned immuneML version declares dependency bounds incompatible with this package's
NumPy 2 requirement; this is a tested source-level experiment, not a supported
ordinary pip co-installation. See the validation document for exact setup.

On all 100 example repertoires, the continuous 3-mer pipeline measured 41.36 s
versus 14.26 s (2.90x). Including TSV ingestion and repertoire preparation,
medians were 55.96 s versus 28.97 s (1.93x). Three fresh processes per backend
matched CSR values and structure, features, model coefficients and predictions
exactly. The final feature matrices occupy the same memory; RSS was not measured.
Avoiding full-vocabulary label generation explains the gain, rather than a
measured SIMD-only advantage.

## Supported contracts

The primitive adapters below remain independently usable. The explicit application
bridges above connect the MotifBoost and immuneML primitives to upstream pipelines.

| Adapter | Provided | Left to the application |
| --- | --- | --- |
| MotifBoost | Boundary-aware k-mers, nonnegative integer weights, most-significant-first feature order, separate normalization per k | Feature-cache integration, TF-IDF, augmentation, multiprocessing and classifier training |
| immuneML | Continuous unprefixed k-mer labels and original sequence IDs; no full-vocabulary string expansion | Mapping sequence IDs to repertoire IDs, vectorizer, V/J/locus prefixes, gapped/IMGT features, normalization |
| DeepRC | Selected rows as int8 codes padded with -1 and their lengths; NCL/LNC layout | Dataset replacement, random sampling, sequence counts/scaling, HDF5 loading and Torch transfer |
| Scirpy | Symmetric unnormalized Hamming cutoff CSR with distance+1 values | AnnData integration, rectangular comparisons, other distances and normalized scores |

`SequenceBatch` defaults to `ACDEFGHIKLMNPQRSTVWY`. Pass `alphabet=` with the exact
order expected by the consuming tool; in particular, copy DeepRC's dataset alphabet
order. Unknown/non-ASCII characters raise ValueError. To retain `X` or `*`, include
it explicitly in the alphabet and confirm that the consumer uses the same codes.
The MotifBoost adapter defaults to `@` as its reserved boundary symbol.

Rows shorter than k produce no k-mers. Empty selections are supported. MotifBoost
zero-total feature blocks are NaN, matching the original normalization. Weight
validation rejects totals that cannot remain exact in float64 integer arithmetic.
Dense motif outputs have an explicit feature budget. Scirpy uses a dense temporary
per sequence-length group and rejects groups beyond `max_group_pairs`; it is not
an unbounded-memory nearest-neighbor solution.

`nbytes` counts packed storage and one offset array, excluding Python object
headers. Application adapters may unpack temporary buffers; packing does not imply
that every computation or the process RSS becomes smaller.

## Checks and measurements

```sh
pip install -e './packages/tightarray-immune[test]'
python -m pytest -q packages/tightarray-immune/tests
python -m mypy --strict packages/tightarray-immune/src
```

Independent contract tests cover windows, empty/short rows, invalid symbols,
weights, feature budgets, padding, selection order and sparse-distance semantics.
Four additional upstream comparisons ran locally and passed: actual MotifBoost
and immuneML functions, DeepRC's resident `get_sample`, and Scirpy's supplied
1,550-sequence reference matrix. They require the pinned clones and application
dependencies described in [the pilot suite](../../benchmarks/bio/README.md).

```sh
export BIO_PILOT_ROOT=/path/to/local/pilots
export MPLCONFIGDIR="$BIO_PILOT_ROOT/mpl"
export NUMBA_NUM_THREADS=1
export MLFLOW_DISABLE_AGENT_HINT=1
python -m pytest -q packages/tightarray-immune/tests
python packages/tightarray-immune/benchmarks/motifboost.py /tmp/motifboost-result.json
```

The upstream tests skip when BIO_PILOT_ROOT is unset. CI runs the independent tests
and strict type checking without installing the four application stacks. The
packaged-adapter MotifBoost measurement is recorded separately in
[benchmarks/motifboost-result.json](benchmarks/motifboost-result.json); earlier
pilot timings should not be treated as timings of this package.

On the same 1,550-sequence fixture, the packaged string-input path measured
6.266 ms original versus 0.682 ms adapter (9.19x), including encoding. With
resident packed input it measured 8.034 ms versus 0.342 ms (23.51x). Ten
alternating-order samples were taken after warmup in one macOS arm64 Python 3.12
process. Outputs matched exactly. These are feature-extraction timings, not
training speedups or evidence of a packing-only advantage. Retained payload plus
indices is 28,408 bytes for this adapter versus 26,460 bytes upstream. One offset
array reduces the earlier prototype's 40,800 bytes, but storage is still larger
than upstream.

## Numba belongs in the core integration layer

The optional [`tightarray.numba`](../../docs/numba.md) integration provides explicit
native descriptors and checked load/store helpers for fixed-width packed arrays.
It does not automatically compile these immune adapters or upstream classifiers.
Writes outside the existing bit width raise `ValueError`; compiled code does not
widen storage automatically. Install the core's `numba` extra when using those
helpers. No Numba dependency is added to this adapter package.
