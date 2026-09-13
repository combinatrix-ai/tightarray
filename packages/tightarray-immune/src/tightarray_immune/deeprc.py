"""Selected sequences to DeepRC's padded integer input contract."""

import operator
from collections.abc import Sequence
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from .sequences import SequenceBatch


def padded_batch(
    batch: SequenceBatch,
    indices: Sequence[int],
    *,
    layout: Literal["NCL", "LNC"] = "NCL",
) -> tuple[NDArray[np.int8], NDArray[np.int64]]:
    """Return codes padded with -1 and true lengths, preserving selection order.

    Use the exact dataset amino-acid alphabet order when creating batch. Counts,
    scaling, random sampling and torch transfer stay in the dataset/collate layer.
    An empty selection returns a (0, 0) matrix and empty lengths.
    """
    if len(batch.alphabet) > 128:
        raise ValueError("DeepRC int8 input requires at most 128 symbols")
    if layout not in ("NCL", "LNC"):
        raise ValueError("layout must be NCL or LNC")
    selected = [operator.index(index) for index in indices]
    if any(index < 0 or index >= len(batch) for index in selected):
        raise IndexError("sequence index out of range")
    lengths = batch.lengths[selected]
    output = np.full((len(selected), int(lengths.max(initial=0))), -1, dtype=np.int8)
    for row, index in enumerate(selected):
        codes = batch.row_codes(index)
        output[row, : len(codes)] = codes
    return output if layout == "NCL" else output.T, lengths
