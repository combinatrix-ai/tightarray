"""Optional checks against the pinned local clones from benchmarks/bio."""

import os
from pathlib import Path

import numpy as np
import pytest
from tightarray_immune import SequenceBatch
from tightarray_immune.deeprc import padded_batch
from tightarray_immune.immuneml import continuous_kmers
from tightarray_immune.motifboost import ngram_features
from tightarray_immune.scirpy import hamming_distance

pytestmark = pytest.mark.skipif(
    "BIO_PILOT_ROOT" not in os.environ,
    reason="requires pinned upstream clones and optional application dependencies",
)


@pytest.fixture
def root(monkeypatch):
    root = Path(os.environ["BIO_PILOT_ROOT"])
    for name in ("immuneML", "DeepRC", "MotifBoost"):
        monkeypatch.syspath_prepend(str(root / "repos" / name))
    return root


@pytest.fixture
def tcrs(root):
    path = (
        root
        / "repos/scirpy/src/scirpy/tests/data/hamming_test_data/hamming_WU3k_seqs.npy"
    )
    return np.load(path, allow_pickle=False).tolist()


def test_motifboost_original(tcrs, root):
    from motifboost.methods.motif import ngram_features as original

    weights = np.arange(len(tcrs), dtype=np.int64) % 5 + 1
    np.testing.assert_array_equal(
        ngram_features(tcrs, weights), original(tcrs, count_weights=weights)
    )


def test_immuneml_original(tcrs, root):
    import bionumpy as bnp
    from immuneML.encodings.kmer_frequency.BNPSequenceEncodingStrategies import (
        encode_continuous_kmer,
    )

    encoded = bnp.as_encoded_array(tcrs, bnp.AminoAcidEncoding)
    alphabet = bytes(encoded.encoding._alphabet).decode("ascii")
    actual = continuous_kmers(SequenceBatch(tcrs, alphabet=alphabet), 3)
    expected = encode_continuous_kmer(encoded, 3)
    for a, b in zip(actual, expected):
        np.testing.assert_array_equal(a, b)


def test_scirpy_reference(tcrs, root):
    from scipy.sparse import load_npz

    path = (
        root
        / "repos/scirpy/src/scirpy/tests/data/hamming_test_data/hamming_WU3k_csr_result.npz"
    )
    actual = hamming_distance(SequenceBatch(tcrs))
    expected = load_npz(path)
    assert actual.shape == expected.shape
    assert (actual != expected).nnz == 0


def test_deeprc_original(root, tmp_path):
    import h5py
    from deeprc.dataset_readers import RepertoireDataset, no_sequence_count_scaling

    sequences = ["ACD", "W", "A"]
    codes = np.array([[0, 1, 2], [18, -1, -1], [0, -1, -1]], dtype=np.int8)
    path = tmp_path / "empty.h5"
    with h5py.File(path, "w"):
        pass
    original = RepertoireDataset.__new__(RepertoireDataset)
    original.filepath = str(path)
    original.sample_sequences_start_end = np.array([[0, 3]])
    original.sequences_hdf5_key = "sequences"
    original.sequence_counts_hdf5_key = "sequence_counts"
    original.sequence_counts_scaling_fn = no_sequence_count_scaling
    original.sampledata = {
        "sequences": codes,
        "seq_lens": np.array([3, 1, 1]),
        "sequence_counts": np.array([2, 3, 5]),
    }
    for layout in ("NCL", "LNC"):
        original.inputformat = layout
        actual = padded_batch(SequenceBatch(sequences), [0, 1, 2], layout=layout)
        expected = original.get_sample(0)
        for a, b in zip(actual, expected[:2]):
            np.testing.assert_array_equal(a, b)
