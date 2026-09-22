"""Actual immuneML repertoire encoding/normalization/classifier opt-in study.

Use the pinned sparse source snapshot plus the portable dispatch patch; this is
an explicit source-level NumPy2 experiment, not a supported pip co-install.
"""

import argparse
import gzip
import hashlib
import importlib.metadata
import json
import os
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path

UPSTREAM = "24d74abb2d30b081f9d6359a688a3e827c983e44"
DEFAULT_DATA = "/Volumes/Shared/local/repos/tightarray-bio-pilots/repos/DeepRC/deeprc/datasets/example_dataset"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def guards(upstream, data):
    import tightarray._core as core

    root = Path(__file__).resolve().parents[2]
    paths = [
        Path(__file__),
        Path(core.__file__),
        root / "benchmarks/bio/patches/immuneml-continuous-aa.patch",
    ]
    for base in (
        root / "tightarray",
        root / "packages/tightarray-immune/src",
        upstream / "immuneML",
        upstream / "scripts",
    ):
        paths += list(base.rglob("*.py"))
    paths += list((root / "tightarray").glob("*.h")) + list(
        (root / "tightarray").glob("*.c")
    )
    paths += [data / "metadata.tsv"] + sorted((data / "repertoires").glob("*.tsv"))
    return {str(p): digest(p.read_bytes()) for p in paths}


def prepare(data, out, count=100, sequence_limit=0):
    import pandas as pd
    from immuneML.data_model.datasets.RepertoireDataset import RepertoireDataset
    from immuneML.data_model.SequenceSet import Repertoire
    from immuneML.environment.LabelConfiguration import LabelConfiguration
    from sklearn.model_selection import train_test_split

    metadata = pd.read_csv(data / "metadata.tsv", sep="\t").iloc[:count]
    label_name = "binary_target_1"
    label_config = LabelConfiguration()
    label_config.add_label(label_name, ["+", "-"], positive_class="+")
    repertoires, sequence_count, hashes = [], 0, {}
    for row in metadata.to_dict(orient="records"):
        path = data / "repertoires" / row["ID"]
        frame = pd.read_csv(path, sep="\t")
        if sequence_limit:
            frame = frame.iloc[:sequence_limit]
        sequences = frame.amino_acid.tolist()
        sequence_count += len(sequences)
        hashes[path.name] = digest(path.read_bytes())
        rep = Repertoire.build(
            out,
            {label_name: row[label_name]},
            identifier=path.stem,
            cdr3_aa=sequences,
            locus=["TRB"] * len(sequences),
            duplicate_count=frame.templates.astype(int).tolist(),
        )
        repertoires.append(rep)
    indices = list(range(len(repertoires)))
    train_ids, test_ids = train_test_split(
        indices, test_size=0.2, random_state=42, stratify=metadata[label_name]
    )
    train = RepertoireDataset(
        repertoires=[repertoires[i] for i in train_ids], identifier="train"
    )
    test = RepertoireDataset(
        repertoires=[repertoires[i] for i in test_ids], identifier="test"
    )
    return (
        train,
        test,
        label_config,
        {
            "sequences": sequence_count,
            "repertoires": len(repertoires),
            "train_ids": [repertoires[i].identifier for i in train_ids],
            "test_ids": [repertoires[i].identifier for i in test_ids],
            "dataset_sha256": hashes,
        },
    )


def matrix_identity(encoded):
    matrix = encoded.examples.tocsr()
    return {
        "shape": list(matrix.shape),
        "nnz": matrix.nnz,
        "data": digest(matrix.data.tobytes()),
        "indices": digest(matrix.indices.tobytes()),
        "indptr": digest(matrix.indptr.tobytes()),
        "features": digest("\n".join(encoded.feature_names).encode()),
        "labels": encoded.labels,
        "example_ids": encoded.example_ids,
    }


def pipeline(backend, k, upstream, data, count=100, sequence_limit=0, reads="UNIQUE"):
    from immuneML.analysis.data_manipulation.NormalizationType import NormalizationType
    from immuneML.data_model.SequenceParams import RegionType
    from immuneML.encodings.EncoderParams import EncoderParams
    from immuneML.encodings.kmer_frequency.KmerFreqRepertoireEncoder import (
        KmerFreqRepertoireEncoder,
    )
    from immuneML.encodings.kmer_frequency.sequence_encoding.SequenceEncodingType import (
        SequenceEncodingType,
    )
    from immuneML.environment.EnvironmentSettings import EnvironmentSettings
    from immuneML.environment.SequenceType import SequenceType
    from immuneML.ml_methods.classifiers.LogisticRegression import LogisticRegression
    from immuneML.util.ReadsType import ReadsType
    from tightarray_immune.immuneml_integration import configure_encoder

    frozen = guards(upstream, data)
    with tempfile.TemporaryDirectory(prefix="ta-immuneml-pipeline-") as temp:
        temp = Path(temp)
        EnvironmentSettings.set_cache_path(temp / "cache")
        start = time.perf_counter()
        train, test, labels, provenance = prepare(data, temp, count, sequence_limit)
        prepared = time.perf_counter()
        encoder = KmerFreqRepertoireEncoder(
            normalization_type=NormalizationType.RELATIVE_FREQUENCY,
            reads=ReadsType[reads],
            sequence_encoding=SequenceEncodingType.CONTINUOUS_KMER,
            k=k,
            k_left=1,
            k_right=1,
            sequence_type=SequenceType.AMINO_ACID,
            region_type=RegionType.IMGT_CDR3,
            scale_to_unit_variance=True,
            scale_to_zero_mean=False,
        )
        configure_encoder(encoder, backend=backend)
        params = EncoderParams(
            result_path=temp,
            label_config=labels,
            pool_size=1,
            learn_model=True,
            encode_labels=True,
        )
        begin = time.perf_counter()
        encoded_train = encoder.encode(train, params)
        trained = time.perf_counter()
        params.learn_model = False
        encoded_test = encoder.encode(test, params)
        transformed = time.perf_counter()
        classifier = LogisticRegression(
            parameters={"solver": "liblinear", "random_state": 7, "max_iter": 1000}
        )
        label = labels.get_label_object("binary_target_1")
        classifier.fit(encoded_train.encoded_data, label, cores_for_training=1)
        fitted = time.perf_counter()
        predictions = classifier.predict(encoded_test.encoded_data, label)
        probabilities = classifier.predict_proba(encoded_test.encoded_data, label)
        predicted = time.perf_counter()
        result = {
            "backend": backend,
            "k": k,
            "reads": reads,
            "provenance": provenance,
            "times_s": {
                "prepare": prepared - start,
                "prepare_plus_pipeline": predicted - start,
                "train_encode": trained - begin,
                "test_transform": transformed - trained,
                "classifier_fit": fitted - transformed,
                "predict": predicted - fitted,
                "pipeline": predicted - begin,
            },
            "train": matrix_identity(encoded_train.encoded_data),
            "test": matrix_identity(encoded_test.encoded_data),
            "unique_predictions": {
                key: len(set(value)) for key, value in predictions.items()
            },
            "predictions": {key: list(value) for key, value in predictions.items()},
            "probabilities": {
                key: {str(c): vals.tolist() for c, vals in value.items()}
                for key, value in probabilities.items()
            },
            "coefficient_sha256": digest(classifier.model.coef_.tobytes()),
            "intercept_sha256": digest(classifier.model.intercept_.tobytes()),
            "train_csr_bytes": sum(
                x.nbytes
                for x in (
                    encoded_train.encoded_data.examples.data,
                    encoded_train.encoded_data.examples.indices,
                    encoded_train.encoded_data.examples.indptr,
                )
            ),
            "source_sha256": frozen,
        }
    assert frozen == guards(upstream, data)
    return result


def run(args):
    root = Path(__file__).resolve().parents[2]
    env = dict(
        os.environ,
        PYTHONPATH=os.pathsep.join(
            [
                str(args.upstream),
                str(root),
                str(root / "packages/tightarray-immune/src"),
            ]
        ),
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
    )
    samples = []
    with tempfile.TemporaryDirectory() as tmp:
        for k in args.ks:
            reference = None
            names = ["bionumpy", "tightarray"]
            random.Random(8420 + k).shuffle(names)
            for repeat in range(args.repeats):
                for backend in names[repeat % 2 :] + names[: repeat % 2]:
                    output = Path(tmp) / "worker.json"
                    subprocess.run(
                        [
                            sys.executable,
                            str(Path(__file__).resolve()),
                            "--worker",
                            backend,
                            "--upstream",
                            str(args.upstream),
                            "--data",
                            str(args.data),
                            "--ks",
                            str(k),
                            "--count",
                            str(args.count),
                            "--sequence-limit",
                            str(args.sequence_limit),
                            "--output",
                            str(output),
                        ],
                        cwd=tmp,
                        env=env,
                        check=True,
                    )
                    sample = json.loads(output.read_text())
                    identity = {
                        key: sample[key]
                        for key in (
                            "train",
                            "test",
                            "predictions",
                            "probabilities",
                            "coefficient_sha256",
                            "intercept_sha256",
                        )
                    }
                    if reference is None:
                        reference = identity
                    assert reference == identity, "Backend pipeline output differs"
                    sample["repeat"] = repeat
                    samples.append(sample)
                    # Preserve every completed worker even if a later process fails.
                    checkpoint = {
                        "status": "partial",
                        "upstream_commit": UPSTREAM,
                        "requested_ks": args.ks,
                        "requested_repeats": args.repeats,
                        "count": args.count,
                        "samples": samples,
                    }
                    raw = (json.dumps(checkpoint, indent=2) + "\n").encode()
                    pending = args.output.with_name(args.output.name + ".pending")
                    pending.write_bytes(
                        gzip.compress(raw, mtime=0)
                        if args.output.suffix == ".gz"
                        else raw
                    )
                    pending.replace(args.output)
                    print(k, backend, sample["times_s"], flush=True)
    assert all(s["source_sha256"] == samples[0]["source_sha256"] for s in samples)
    return {
        "status": "complete",
        "upstream_commit": UPSTREAM,
        "upstream_materialization": "isolated snapshot of available tracked files; missing documentation helpers fetched from same public commit",
        "dependency_caveat": "Source-level minimal environment uses NumPy2; upstream declared NumPy<=1.26.4/SciPy<=1.12 conflicts with adapter NumPy>=2. Not a supported pip co-install.",
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("numpy", "scipy", "pandas", "scikit-learn", "bionumpy", "dill")
        },
        "scope": "Real immuneML encode/train-vocabulary/test-transform/relative-frequency normalization/variance scaling and LogisticRegression fit+predict. Public DeepRC example repertoires and supplied example binary targets; not clinical validation or nested CV. Pipeline excludes preparation; prepare_plus_pipeline includes it. Upstream cold caching/one-worker Pool included. No feature-matrix memory reduction claimed.",
        "samples": samples,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--upstream", type=Path, default=Path("/tmp/ta-immuneml-integration")
    )
    parser.add_argument("--data", type=Path, default=Path(DEFAULT_DATA))
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--sequence-limit", type=int, default=0)
    parser.add_argument("--ks", nargs="+", type=int, default=[3, 4])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--worker", choices=("bionumpy", "tightarray"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = (
        pipeline(
            args.worker,
            args.ks[0],
            args.upstream,
            args.data,
            args.count,
            args.sequence_limit,
        )
        if args.worker
        else run(args)
    )
    raw = (json.dumps(result, indent=2) + "\n").encode()
    args.output.write_bytes(
        gzip.compress(raw, mtime=0) if args.output.suffix == ".gz" else raw
    )
