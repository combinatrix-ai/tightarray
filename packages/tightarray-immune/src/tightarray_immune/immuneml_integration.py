"""Explicit integration hook for the pinned immuneML repertoire encoder patch.

Importing this module does not patch immuneML or import its optional dependencies.
The default upstream BioNumPy path remains unchanged until configured explicitly.
"""

from collections.abc import Sequence
from typing import Literal, Protocol, cast

import numpy as np
from numpy.typing import NDArray

from .immuneml import continuous_kmers
from .sequences import SequenceBatch

Backend = Literal["bionumpy", "tightarray"]


class _PatchedEncoder(Protocol):
    _tightarray_backend: Backend


def configure_encoder(encoder: object, *, backend: Backend) -> None:
    """Select one backend on an explicitly patched immuneML encoder instance.

    The marker is supplied by the source-pinned portable patch. Keeping the
    selection on the encoder also makes it part of upstream encoding cache keys.
    Unsupported semantics raise when encoding; they never silently lose prefixes.
    """
    if backend not in ("bionumpy", "tightarray"):
        raise ValueError("backend must be bionumpy or tightarray")
    if getattr(encoder, "_tightarray_dispatch_version", None) != 1:
        raise TypeError("apply the pinned immuneML integration patch first")
    cast(_PatchedEncoder, encoder)._tightarray_backend = backend


def encode_continuous_aa(
    sequences: Sequence[str],
    *,
    alphabet: str,
    k: int,
    sequence_encoding: str,
    sequence_type: str,
    locus_labels: Sequence[str] | None = None,
    v_genes: Sequence[str] | None = None,
    k_left: int = 0,
    k_right: int = 0,
    min_gap: int = 0,
    max_gap: int = 0,
) -> tuple[NDArray[np.str_], NDArray[np.int64]]:
    """Return exactly observed continuous labels and original sequence row IDs.

    Sequence extraction/region selection, read-count weights, vectorization,
    normalization, feature scaling and train/test vocabulary remain upstream.
    Conversion from the upstream ragged array is part of integration cost.
    """
    if sequence_type != "AMINO_ACID" or sequence_encoding != "CONTINUOUS_KMER":
        raise NotImplementedError("only continuous amino-acid k-mers are supported")
    if locus_labels is not None or v_genes is not None:
        raise NotImplementedError("locus and gene prefixes are not supported")
    # Upstream ignores these fields for CONTINUOUS_KMER; its default config
    # still has k_left=k_right=1. Reject strategies, not inactive parameters.
    batch = SequenceBatch(sequences, alphabet=alphabet)
    return continuous_kmers(batch, k)
