"""Scirpy-style symmetric Hamming cutoff matrices (distance + 1)."""

import operator

import numpy as np
from scipy.sparse import coo_matrix, csr_matrix

from tightarray import Array

from .sequences import SequenceBatch


def hamming_distance(
    batch: SequenceBatch, *, cutoff: int = 2, max_group_pairs: int = 16_000_000
) -> csr_matrix:
    """Unequal lengths have no edge; duplicates/diagonal have stored value 1.

    This prototype uses a dense intermediate per length group. The explicit pair
    budget rejects oversized groups; a streaming sparse core is future work.
    Rectangular comparisons and normalized Hamming are not implemented.
    """
    cutoff = operator.index(cutoff)
    max_group_pairs = operator.index(max_group_pairs)
    if not 0 <= cutoff <= 254 or max_group_pairs < 0:
        raise ValueError("cutoff must be 0..254 and pair budget nonnegative")
    if not len(batch):
        return csr_matrix((0, 0), dtype=np.uint8)
    bits = max(1, (len(batch.alphabet) - 1).bit_length())
    lanes = 64 // bits
    lengths = batch.lengths
    rows: list[np.ndarray[tuple[int, ...], np.dtype[np.int64]]] = []
    cols: list[np.ndarray[tuple[int, ...], np.dtype[np.int64]]] = []
    values: list[np.ndarray[tuple[int, ...], np.dtype[np.uint8]]] = []
    for length in np.unique(lengths):
        selected = np.flatnonzero(lengths == length).astype(np.int64)
        n = len(selected)
        if n * n > max_group_pairs:
            raise ValueError("length group exceeds max_group_pairs")
        width = max(lanes, ((int(length) + lanes - 1) // lanes) * lanes)
        codes = np.zeros((n, width), dtype=np.uint8)
        for row, index in enumerate(selected):
            codes[row, : int(length)] = batch.row_codes(int(index))
        # Force the alphabet width without exposing bit-width types in the adapter.
        from typing import Literal, cast

        packed = Array(
            codes.ravel(),
            bits=cast(Literal[1, 2, 3, 4, 5, 6, 7, 8], bits),
            layout="word-aligned",
        )
        distances = np.frombuffer(
            packed._hamming_rows(width, cutoff), dtype=np.uint8
        ).reshape(n, n)
        r, c = np.nonzero(distances)
        rows.append(selected[r])
        cols.append(selected[c])
        values.append(distances[r, c])
    return coo_matrix(
        (np.concatenate(values), (np.concatenate(rows), np.concatenate(cols))),
        shape=(len(batch), len(batch)),
    ).tocsr()
