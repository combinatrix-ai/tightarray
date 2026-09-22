"""Optional actual MotifBoost integration tests; no substitute classifier."""

from importlib.util import find_spec
import numpy as np
import pytest

from tightarray_immune.motifboost_integration import (
    motifboost_backend,
    tightarray_features,
)


def test_supported_contract_rejections():
    for options in (
        {"alphabets": ["A", "A"]},
        {"alphabets": ["AB", "C"]},
        {"void_mark": "AA"},
        {"void_mark": "A"},
        {"ngram_range": (5, 6)},
        {"count_weights": [-1]},
        {"count_weights": [1.5]},
        {"count_weights": np.array([2**63], dtype=np.uint64)},
        {"count_weights": [1, 2]},
    ):
        with pytest.raises(ValueError):
            tightarray_features(["ACD"], **options)


@pytest.mark.skipif(
    find_spec("motifboost") is None, reason="optional external MotifBoost source"
)
@pytest.mark.parametrize("weighted", [False, True])
def test_actual_feature_extractor_weight_tfidf_and_restore(weighted):
    from motifboost.methods import motif
    from motifboost.repertoire import Repertoire

    original = motif.ngram_features
    options = dict(
        alphabets=list("CAD"), void_mark="!", count_weights=[2, 3], ngram_range=(2, 4)
    )
    np.testing.assert_array_equal(
        tightarray_features(["CAD", "AC"], **options),
        original(["CAD", "AC"], **options),
    )
    repertoires = [
        Repertoire("test", str(i), {}, ["ACDEFG", "KLMNP", "ACD"], [i + 1, 2, 3])
        for i in range(4)
    ]
    expected = None
    for backend in ("upstream", "tightarray"):
        with motifboost_backend(backend):
            extractor = motif.MotifFeatureExtractor(
                n_processes=1, tfidf_mode=True, count_weight_mode=weighted
            )
            fit = np.array(
                extractor.fit(repertoires, use_cache=False, save_cache=False)
            )
            transformed = np.array(
                extractor.transform(repertoires, use_cache=False, save_cache=False)
            )
            if expected is None:
                expected = (fit, transformed, extractor.idf)
            else:
                for actual, reference in zip(
                    (fit, transformed, extractor.idf), expected
                ):
                    np.testing.assert_array_equal(actual, reference)
        assert motif.ngram_features is original
    with motifboost_backend("tightarray"):
        with pytest.raises(RuntimeError, match="nested"):
            with motifboost_backend("upstream"):
                pass
    with pytest.raises(RuntimeError), motifboost_backend("tightarray"):
        raise RuntimeError("check scoped restoration")
    assert motif.ngram_features is original


@pytest.mark.skipif(
    find_spec("motifboost") is None, reason="optional external MotifBoost source"
)
def test_actual_classifier_fit_predict_proba():
    from motifboost.methods.motif import MotifBoostClassifier
    from motifboost.repertoire import Repertoire

    expected = None
    for backend in ("upstream", "tightarray"):
        repertoires = [
            Repertoire(
                "test", str(i), {}, ["ACDEFG" if i % 2 else "KLMNP", "ACD"], [i + 1, 2]
            )
            for i in range(8)
        ]
        with motifboost_backend(backend):
            classifier = MotifBoostClassifier(
                n_jobs=1, classifier_method="linear_regression", augmentation_times=0
            )
            classifier.fit(repertoires, [bool(i % 2) for i in range(8)])
            result = classifier.predict_proba(repertoires)
        if expected is None:
            expected = result
        else:
            np.testing.assert_allclose(result, expected, rtol=0, atol=1e-12)
