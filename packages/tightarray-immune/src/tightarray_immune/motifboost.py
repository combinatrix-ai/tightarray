"""MotifBoost feature order, boundary symbols and per-k normalization."""

import operator
from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from .sequences import AMINO_ACIDS, SequenceBatch


class MotifRepertoire:
    """Reusable encoded repertoire; no retained Python string per sequence."""

    def __init__(
        self,
        sequences: Sequence[str],
        *,
        alphabet: str = AMINO_ACIDS,
        boundary: str = "@",
    ) -> None:
        if len(boundary) != 1 or boundary in alphabet:
            raise ValueError("boundary must be one distinct character")
        if any(boundary in sequence for sequence in sequences):
            raise ValueError("input sequences must not contain the boundary symbol")
        # Reversal matches MotifBoost's most-significant-first feature ordering.
        self._batch = SequenceBatch(
            [boundary + s[::-1] + boundary for s in sequences],
            alphabet=boundary + alphabet,
        )

    @property
    def nbytes(self) -> int:
        return self._batch.nbytes

    def features(
        self,
        weights: Sequence[int] | NDArray[np.int64] | None = None,
        *,
        ngram_range: tuple[int, int] = (3, 4),
        max_features: int = 1_000_000,
    ) -> NDArray[np.float64]:
        start, stop = map(operator.index, ngram_range)
        if not 1 <= start < stop:
            raise ValueError("ngram_range must satisfy 1 <= start < stop")
        base = len(self._batch.alphabet)
        max_features = operator.index(max_features)
        # Bound both iteration and dense feature allocation before exponentiation.
        if (
            stop > 64
            or max_features < 1
            or sum(base**k for k in range(start, stop)) > max_features
        ):
            raise ValueError("feature space exceeds max_features")
        counts = (
            np.ones(len(self._batch), dtype=np.int64)
            if weights is None
            else np.asarray(weights)
        )
        if (
            counts.shape != (len(self._batch),)
            or counts.dtype.kind not in "iu"
            or np.any(counts < 0)
        ):
            raise ValueError("weights must be one nonnegative integer per sequence")
        if (
            sum(int(value) for value in counts)
            * max(int(self._batch.lengths.max(initial=0)), 1)
            > 2**53
        ):
            raise ValueError("weighted counts exceed exact float64 integer range")
        blocks: list[NDArray[np.float64]] = []
        for k in range(start, stop):
            codes, rows = self._batch.window_codes(k)
            block = np.bincount(
                codes.astype(np.int64),
                weights=counts[rows].astype(np.float64),
                minlength=base**k,
            ).astype(np.float64)
            total = float(block.sum())
            if total == 0:
                block.fill(np.nan)  # Matches upstream zero-total normalization.
            else:
                block /= total
            blocks.append(block)
        return np.concatenate(blocks)


def ngram_features(
    sequences: Sequence[str],
    weights: Sequence[int] | NDArray[np.int64] | None = None,
    *,
    ngram_range: tuple[int, int] = (3, 4),
) -> NDArray[np.float64]:
    """String input convenience path; encoding cost is included in this call."""
    return MotifRepertoire(sequences).features(weights, ngram_range=ngram_range)
