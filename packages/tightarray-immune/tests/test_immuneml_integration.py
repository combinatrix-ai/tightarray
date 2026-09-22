import numpy as np
import pytest
from tightarray_immune.immuneml_integration import (
    configure_encoder,
    encode_continuous_aa,
)


def encode(sequences, **kwargs):
    return encode_continuous_aa(
        sequences,
        alphabet="ACDE",
        k=2,
        sequence_encoding="CONTINUOUS_KMER",
        sequence_type="AMINO_ACID",
        **kwargs,
    )


def test_observed_labels_and_rows():
    labels, rows = encode(["ACDE", "", "A", "AAAA"])
    assert labels.tolist() == ["AC", "CD", "DE", "AA", "AA", "AA"]
    np.testing.assert_array_equal(rows, [0, 0, 0, 3, 3, 3])


@pytest.mark.parametrize(
    "kwargs",
    [{"locus_labels": ["TRB"]}, {"v_genes": ["V1"]}],
)
def test_unsupported_prefix_rejected(kwargs):
    with pytest.raises(NotImplementedError):
        encode(["ACDE"], **kwargs)


@pytest.mark.parametrize(
    "encoding", ["GAPPED_KMER", "IMGT_CONTINUOUS_KMER", "V_GENE_CONT_KMER"]
)
def test_unsupported_encoding_rejected(encoding):
    with pytest.raises(NotImplementedError):
        encode_continuous_aa(
            ["ACDE"],
            alphabet="ACDE",
            k=2,
            sequence_encoding=encoding,
            sequence_type="AMINO_ACID",
        )


def test_explicit_patch_marker_and_optin():
    class Encoder:
        _tightarray_dispatch_version = 1

    encoder = Encoder()
    configure_encoder(encoder, backend="tightarray")
    assert encoder._tightarray_backend == "tightarray"
    configure_encoder(encoder, backend="bionumpy")
    assert encoder._tightarray_backend == "bionumpy"
    with pytest.raises(TypeError):
        configure_encoder(object(), backend="tightarray")


def test_continuous_ignores_upstream_default_gap_fields():
    labels, rows = encode(["ACDE"], k_left=1, k_right=1, min_gap=0, max_gap=0)
    expected_labels, expected_rows = encode(["ACDE"])
    np.testing.assert_array_equal(labels, expected_labels)
    np.testing.assert_array_equal(rows, expected_rows)


def test_actual_patched_encoder_cache_and_deepcopy():
    import copy
    import importlib

    pytest.importorskip("immuneML")
    module = importlib.import_module(
        "immuneML.encodings.kmer_frequency.KmerFreqRepertoireEncoder"
    )
    cls = module.KmerFreqRepertoireEncoder
    if getattr(cls, "_tightarray_dispatch_version", None) != 1:
        pytest.skip("requires the explicitly patched pinned upstream encoder")
    from types import SimpleNamespace

    from immuneML.analysis.data_manipulation.NormalizationType import NormalizationType
    from immuneML.data_model.SequenceParams import RegionType
    from immuneML.encodings.EncoderParams import EncoderParams
    from immuneML.encodings.kmer_frequency.sequence_encoding.SequenceEncodingType import (
        SequenceEncodingType,
    )
    from immuneML.environment.LabelConfiguration import LabelConfiguration
    from immuneML.environment.SequenceType import SequenceType
    from immuneML.util.ReadsType import ReadsType

    encoder = cls(
        normalization_type=NormalizationType.RELATIVE_FREQUENCY,
        reads=ReadsType.UNIQUE,
        sequence_encoding=SequenceEncodingType.CONTINUOUS_KMER,
        k=3,
        k_left=1,
        k_right=1,
        sequence_type=SequenceType.AMINO_ACID,
        region_type=RegionType.IMGT_CDR3,
    )
    params = EncoderParams(label_config=LabelConfiguration())
    dataset = SimpleNamespace(identifier="same")
    configure_encoder(encoder, backend="bionumpy")
    baseline = encoder._prepare_caching_params(dataset, params)
    configure_encoder(encoder, backend="tightarray")
    packed = encoder._prepare_caching_params(dataset, params)
    assert baseline != packed
    clone = copy.deepcopy(encoder)
    assert clone._tightarray_backend == "tightarray"
    assert clone._prepare_caching_params(dataset, params) == packed


def test_actual_weighted_repertoire_default_parameters(tmp_path):
    pytest.importorskip("immuneML")
    from immuneML.analysis.data_manipulation.NormalizationType import NormalizationType
    from immuneML.data_model.SequenceParams import RegionType
    from immuneML.data_model.SequenceSet import Repertoire
    from immuneML.encodings.EncoderParams import EncoderParams
    from immuneML.encodings.kmer_frequency.KmerFreqRepertoireEncoder import (
        KmerFreqRepertoireEncoder,
    )
    from immuneML.encodings.kmer_frequency.sequence_encoding.SequenceEncodingType import (
        SequenceEncodingType,
    )
    from immuneML.environment.SequenceType import SequenceType
    from immuneML.util.ReadsType import ReadsType

    if getattr(KmerFreqRepertoireEncoder, "_tightarray_dispatch_version", None) != 1:
        pytest.skip("requires the explicitly patched pinned upstream encoder")
    rep = Repertoire.build(
        tmp_path,
        {"target": "+"},
        identifier="weighted",
        cdr3_aa=["ACDE", "AAA", "A"],
        locus=["TRB"] * 3,
        duplicate_count=[2, 3, 4],
    )
    encoder = KmerFreqRepertoireEncoder(
        normalization_type=NormalizationType.RELATIVE_FREQUENCY,
        reads=ReadsType.ALL,
        sequence_encoding=SequenceEncodingType.CONTINUOUS_KMER,
        k=2,
        k_left=1,
        k_right=1,
        sequence_type=SequenceType.AMINO_ACID,
        region_type=RegionType.IMGT_CDR3,
    )
    params = EncoderParams(encode_labels=False)
    baseline = encoder._encode_single_repertoire(rep, params, False)
    configure_encoder(encoder, backend="tightarray")
    packed = encoder._encode_single_repertoire(rep, params, False)
    np.testing.assert_array_equal(baseline[0], packed[0])
    np.testing.assert_array_equal(baseline[1], packed[1])
    np.testing.assert_array_equal(packed[1], [2, 2, 2, 3, 3])
    assert baseline[2:] == packed[2:]
    with pytest.raises(NotImplementedError):
        encoder._encode_single_repertoire(rep, params, True)
    configure_encoder(encoder, backend="bionumpy")
    prefixed = encoder._encode_single_repertoire(rep, params, True)
    assert all("TRB" in label for label in prefixed[0])
