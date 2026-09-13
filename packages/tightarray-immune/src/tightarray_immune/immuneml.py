"""Continuous, unprefixed k-mer labels accepted by immuneML's vectorizer."""

import numpy as np
from numpy.typing import NDArray

from .sequences import SequenceBatch


def continuous_kmers(
    batch: SequenceBatch, k: int
) -> tuple[NDArray[np.str_], NDArray[np.int64]]:
    """Return observed labels and original row IDs, without the full vocabulary.

    Locus/V-gene prefixes, IMGT positions and repertoire assignment remain with
    the caller. Choose the same alphabet as the originating immuneML data.
    """
    codes, rows = batch.window_codes(k)
    alphabet = np.array(list(batch.alphabet), dtype=np.str_)
    base = len(alphabet)
    labels = alphabet[codes % base]
    for position in range(1, k):
        labels = np.char.add(labels, alphabet[(codes // (base**position)) % base])
    return labels, rows
