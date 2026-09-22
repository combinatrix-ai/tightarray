"""Explicit, scoped integration with MotifBoost's real feature extractor.

The upstream module-level feature callable is changed only inside the context.
Create/fit/predict the classifier inside it; fork workers inherit the selection.
This process-wide switch is not safe for concurrent threads choosing backends.
Within the supported input contract, classifier, TFIDF, cache, augmentation,
and weight behavior are preserved. The packed adapter requires a distinct ASCII
alphabet and a single distinct boundary character absent from sequences; integer
nonnegative counts; total weighted positions <=2**53; and at most 1,000,000
dense features. Unsupported upstream configurations raise rather than fall back.
Nested contexts are rejected; concurrent use across threads is unsupported.
"""

from collections.abc import Iterator
from contextlib import contextmanager
import importlib
from typing import Literal, Protocol, cast

import numpy as np
from numpy.typing import NDArray

from .motifboost import MotifRepertoire
from .sequences import AMINO_ACIDS

Backend = Literal["upstream", "tightarray"]
_active = False


class _FeatureFunction(Protocol):
    def __call__(
        self,
        seqs: list[str],
        alphabets: list[str] | None = None,
        void_mark: str | None = None,
        count_weights: list[int] | NDArray[np.uint16] | None = None,
        ngram_range: tuple[int, int] = (3, 4),
    ) -> NDArray[np.float64]: ...


class _Module(Protocol):
    ngram_features: _FeatureFunction


def tightarray_features(
    seqs: list[str],
    alphabets: list[str] | None = None,
    void_mark: str | None = None,
    count_weights: list[int] | NDArray[np.uint16] | None = None,
    ngram_range: tuple[int, int] = (3, 4),
) -> NDArray[np.float64]:
    if alphabets is not None and any(len(symbol) != 1 for symbol in alphabets):
        raise ValueError("each alphabet entry must be one ASCII character")
    repertoire = MotifRepertoire(
        seqs,
        alphabet=AMINO_ACIDS if alphabets is None else "".join(alphabets),
        boundary="@" if void_mark is None else void_mark,
    )
    weights = None if count_weights is None else np.asarray(count_weights)
    return repertoire.features(weights, ngram_range=ngram_range)


@contextmanager
def motifboost_backend(backend: Backend = "tightarray") -> Iterator[None]:
    """Select numeric features for actual upstream fit/transform/predict_proba.

    MotifBoost is optional and imported only when this context is entered.
    The prior function is restored even if training or prediction fails.
    """
    global _active
    if _active:
        raise RuntimeError("nested MotifBoost backend contexts are unsupported")
    if backend not in ("upstream", "tightarray"):
        raise ValueError("backend must be upstream or tightarray")
    module = cast(_Module, importlib.import_module("motifboost.methods.motif"))
    original = module.ngram_features
    _active = True
    try:
        if backend == "tightarray":
            module.ngram_features = tightarray_features
        yield
    finally:
        module.ngram_features = original
        _active = False
