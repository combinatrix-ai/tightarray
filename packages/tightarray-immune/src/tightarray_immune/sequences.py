"""Validated, packed storage shared by the application adapters."""

import operator
from collections.abc import Sequence
from typing import Literal, cast

import numpy as np
from numpy.typing import NDArray

from tightarray import Array

AMINO_ACIDS = "ACDEFGHIKLMNPQRSTVWY"


class SequenceBatch:
    """An immutable-by-interface batch of ASCII sequences and their row offsets.

    Unknown symbols are rejected. Supply the tool's exact alphabet order explicitly
    when it differs from AMINO_ACIDS. No silent replacement of unknown residues.
    """

    def __init__(
        self, sequences: Sequence[str], *, alphabet: str = AMINO_ACIDS
    ) -> None:
        if (
            not alphabet.isascii()
            or not 2 <= len(alphabet) <= 256
            or len(set(alphabet)) != len(alphabet)
        ):
            raise ValueError("alphabet must contain 2..256 distinct ASCII characters")
        self._alphabet = alphabet
        lengths = np.fromiter(
            (len(s) for s in sequences), dtype=np.int64, count=len(sequences)
        )
        self._offsets: NDArray[np.int64] = np.concatenate(
            (np.zeros(1, dtype=np.int64), np.cumsum(lengths))
        )
        try:
            raw = np.frombuffer("".join(sequences).encode("ascii"), dtype=np.uint8)
        except UnicodeEncodeError as exc:
            raise ValueError("sequences must be ASCII") from exc
        lookup = np.full(256, -1, dtype=np.int16)
        lookup[np.frombuffer(alphabet.encode("ascii"), dtype=np.uint8)] = np.arange(
            len(alphabet)
        )
        codes = lookup[raw]
        if np.any(codes < 0):
            raise ValueError("sequence contains a symbol outside the alphabet")
        self._data = Array(
            codes.astype(np.uint8),
            bits=cast(
                Literal[1, 2, 3, 4, 5, 6, 7, 8], (len(alphabet) - 1).bit_length()
            ),
        )

    def __len__(self) -> int:
        return len(self._offsets) - 1

    @property
    def alphabet(self) -> str:
        return self._alphabet

    @property
    def lengths(self) -> NDArray[np.int64]:
        return np.diff(self._offsets)

    @property
    def nbytes(self) -> int:
        """Retained packed payload plus offsets; excludes Python object headers."""
        return self._data.nbytes + self._offsets.nbytes

    def row_codes(self, index: int) -> NDArray[np.uint8]:
        index = operator.index(index)
        if not 0 <= index < len(self):
            raise IndexError("sequence index out of range")
        start, stop = int(self._offsets[index]), int(self._offsets[index + 1])
        return np.frombuffer(self._data[start:stop].tobytes(), dtype=np.uint8)

    def window_codes(self, k: int) -> tuple[NDArray[np.uint64], NDArray[np.int64]]:
        """Little-significance-first positional codes and original sequence IDs.

        Windows never cross a sequence boundary. Rows shorter than k contribute
        no windows. The underlying private core currently requires radix**k < 2**64.
        """
        k = operator.index(k)
        codes = np.frombuffer(
            self._data._rolling_codes(k, len(self._alphabet)), dtype=np.uint64
        )
        sizes = np.maximum(self.lengths - k + 1, 0)
        rows = np.repeat(np.arange(len(self), dtype=np.int64), sizes)
        relative_starts = np.cumsum(sizes) - sizes
        positions = np.repeat(self._offsets[:-1] - relative_starts, sizes) + np.arange(
            len(rows), dtype=np.int64
        )
        return codes[positions], rows
