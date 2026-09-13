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

## Supported contracts

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

Twenty-one independent contract tests cover windows, empty/short rows, invalid symbols,
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

Numba support is a useful next step, but is not implemented by this adapter.
NumPy conversion/Array API conformance alone does not make a packed array usable
inside `@njit`. Numba has an explicit [custom-type extension mechanism](https://numba.readthedocs.io/en/stable/extending/interval-example.html).

A first implementation should support read-only 1D access, length and iteration,
with distinct lowering for packed and word-aligned layouts. It needs a native
storage descriptor, correct owner lifetime management, slice offsets, bounds
behavior and protection against reallocation while compiled code uses the storage.
The acceptance test is a custom `@njit` loop over packed data without first
materializing a uint8 array, compared with Python and NumPy for time and memory.
Ragged offsets are the next useful step for repertoire-level loops. Writes and
automatic bit-width growth need a separate mutation/lifetime contract.
