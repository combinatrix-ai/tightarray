"""Explicit adapters; importing this package never patches upstream libraries."""

from .sequences import AMINO_ACIDS, SequenceBatch

__all__ = ["AMINO_ACIDS", "SequenceBatch"]
