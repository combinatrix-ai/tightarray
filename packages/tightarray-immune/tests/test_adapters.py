import numpy as np
import pytest
from tightarray_immune import SequenceBatch
from tightarray_immune.deeprc import padded_batch
from tightarray_immune.immuneml import continuous_kmers
from tightarray_immune.motifboost import MotifRepertoire
from tightarray_immune.scirpy import hamming_distance


@pytest.mark.parametrize("seqs", [[], [""], ["", "A", "ACD", "", "WYAC"]])
def test_sequence_windows(seqs):
    batch = SequenceBatch(seqs)
    for k in (1, 2, 3, 7):
        labels, rows = continuous_kmers(batch, k)
        assert labels.tolist() == [
            s[i : i + k] for s in seqs for i in range(max(0, len(s) - k + 1))
        ]
        assert rows.tolist() == [
            r for r, s in enumerate(seqs) for _ in range(max(0, len(s) - k + 1))
        ]
    lengths = batch.lengths
    lengths[:] = 99
    assert batch.lengths.tolist() == list(map(len, seqs))


@pytest.mark.parametrize(
    "alphabet,seqs", [("AA", ["A"]), ("A", ["A"]), ("AC", ["X"]), ("AC", ["あ"])]
)
def test_invalid_encoding(alphabet, seqs):
    with pytest.raises(ValueError):
        SequenceBatch(seqs, alphabet=alphabet)


@pytest.mark.parametrize("k", [0, -1, 100])
def test_invalid_window(k):
    with pytest.raises(ValueError):
        SequenceBatch([]).window_codes(k)


def test_weighted_motifs():
    seqs = ["", "A", "ACDE", "WYAC", "GGG"]
    weights = [2, 1, 5, 3, 4]
    batch = MotifRepertoire(seqs)
    result = batch.features(weights, ngram_range=(2, 5))
    alphabet = "@ACDEFGHIKLMNPQRSTVWY"
    blocks = []
    for k in range(2, 5):
        expected = np.zeros(21**k)
        for seq, weight in zip(seqs, weights):
            seq = "@" + seq + "@"
            for start in range(max(0, len(seq) - k + 1)):
                code = sum(
                    alphabet.index(c) * 21 ** (k - j - 1)
                    for j, c in enumerate(seq[start : start + k])
                )
                expected[code] += weight
        blocks.append(expected / expected.sum())
    np.testing.assert_array_equal(result, np.concatenate(blocks))
    assert np.isnan(batch.features([0] * len(seqs))).all()
    assert np.isnan(MotifRepertoire([]).features()).all()


@pytest.mark.parametrize("weights", [[-1], [1.5], [1, 2], [2**54]])
def test_invalid_weights(weights):
    with pytest.raises(ValueError):
        MotifRepertoire(["A"]).features(weights)


def test_feature_budget_and_boundaries():
    with pytest.raises(ValueError):
        MotifRepertoire(["A@C"])
    for bounds in [(0, 2), (3, 3), (3, 999999)]:
        with pytest.raises(ValueError):
            MotifRepertoire(["A"]).features(ngram_range=bounds)
    with pytest.raises(ValueError):
        MotifRepertoire(["A"]).features(max_features=3)


def test_deeprc_selection_and_layout():
    batch = SequenceBatch(["ACD", "W", ""])
    codes, lengths = padded_batch(batch, [1, 0, 1, 2])
    expected = np.array(
        [[18, -1, -1], [0, 1, 2], [18, -1, -1], [-1, -1, -1]], dtype=np.int8
    )
    np.testing.assert_array_equal(codes, expected)
    assert lengths.tolist() == [1, 3, 1, 0]
    np.testing.assert_array_equal(
        padded_batch(batch, [1, 0, 1, 2], layout="LNC")[0], expected.T
    )
    assert padded_batch(batch, [])[0].shape == (0, 0)
    for index in (-1, 3):
        with pytest.raises(IndexError):
            padded_batch(batch, [index])


@pytest.mark.parametrize("cutoff", [0, 1, 2])
def test_sparse_distance(cutoff):
    seqs = ["AAA", "ACA", "CCC", "AAA", "AC", "C", ""]
    actual = hamming_distance(SequenceBatch(seqs), cutoff=cutoff).toarray()
    expected = np.zeros(actual.shape, dtype=np.uint8)
    for i, a in enumerate(seqs):
        for j, b in enumerate(seqs):
            distance = sum(x != y for x, y in zip(a, b))
            if len(a) == len(b) and distance <= cutoff:
                expected[i, j] = distance + 1
    np.testing.assert_array_equal(actual, expected)
    assert hamming_distance(SequenceBatch([])).shape == (0, 0)
    with pytest.raises(ValueError):
        hamming_distance(SequenceBatch(["A", "C"]), max_group_pairs=3)


def test_retained_sequence_storage_is_packed():
    batch = SequenceBatch(["ACDE" * 25])
    assert (
        batch.nbytes < 100
    )  # Packed payload plus offsets is smaller than uint8 payload alone.
