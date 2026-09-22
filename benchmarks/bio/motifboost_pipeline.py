"""Real MotifBoost load/fit/predict_proba integration with explicit backends.

Requires external pinned MotifBoost and DeepRC fixture, never vendors either.
Run each backend in a fresh process; imports and JIT warmup excluded explicitly.
"""

from __future__ import annotations
import argparse
from contextlib import contextmanager
import numpy as np
from numpy.typing import NDArray
from tightarray_immune.sequences import AMINO_ACIDS
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import random
import resource
import subprocess
import sys
import tempfile
import time

PIN = "0fd515b787cd0834c02becefc772bc6059247d5a"
DEEP_PIN = "108d08d8cf2d2d69eb3f6caef1aa04d624dec871"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _numpy_features(
    seqs: list[str],
    alphabets: list[str] | None = None,
    void_mark: str | None = None,
    count_weights: list[int] | NDArray[np.uint16] | None = None,
    ngram_range: tuple[int, int] = (3, 4),
) -> NDArray[np.float64]:
    """Numeric uint8 ablation with identical boundary/order/normalization."""
    alphabet = AMINO_ACIDS if alphabets is None else "".join(alphabets)
    boundary = "@" if void_mark is None else void_mark
    mapping = {ch: i for i, ch in enumerate(boundary + alphabet)}
    arrays = [
        np.array([mapping[c] for c in boundary + s + boundary], dtype=np.uint8)
        for s in seqs
    ]
    weights = (
        np.ones(len(seqs), dtype=np.int64)
        if count_weights is None
        else np.asarray(count_weights, dtype=np.int64)
    )
    blocks = []
    base = len(mapping)
    for k in range(*ngram_range):
        counts = np.zeros(base**k, dtype=np.int64)
        powers = base ** np.arange(k - 1, -1, -1, dtype=np.int64)
        for row, weight in zip(arrays, weights):
            if len(row) >= k:
                codes = np.lib.stride_tricks.sliding_window_view(row, k) @ powers
                counts += np.bincount(codes, minlength=base**k) * weight
        blocks.append(counts.astype(np.float64) / counts.sum())
    return np.concatenate(blocks)


@contextmanager
def _selected_backend(backend):
    from motifboost.methods import motif
    from tightarray_immune.motifboost_integration import motifboost_backend

    if backend != "numpy":
        with motifboost_backend(backend):
            yield
        return
    # Benchmark-only ablation, intentionally not a supported package backend.
    with motifboost_backend("upstream"):
        original = motif.ngram_features
        try:
            motif.ngram_features = _numpy_features
            yield
        finally:
            motif.ngram_features = original


def worker(args):
    import numpy as np
    from motifboost.methods.motif import MotifBoostClassifier, ngram_features
    from motifboost.repertoire import Repertoire

    # Warm original Numba kernel before fork, identically for every backend.
    ngram_features(["ACDEFGHIK"], count_weights=[2])
    rows = json.loads((args.dataset / "samples.json").read_text())
    rss_scale = 1 if sys.platform == "darwin" else 1024
    baseline_peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * rss_scale
    with _selected_backend(args.backend):
        started = time.perf_counter()
        data = [
            Repertoire.load(str(args.dataset), "deeprc-example", r["id"]) for r in rows
        ]
        loaded = time.perf_counter()
        train = data[: args.train]
        test = data[args.train :]
        model = MotifBoostClassifier(
            classifier_method=args.classifier,
            n_jobs=1,
            augmentation_times=0,
            tfidf_mode=args.tfidf,
        )
        model.fit(train, [r["label"] for r in rows[: args.train]])
        fitted = time.perf_counter()
        probabilities = model.predict_proba(test)
        predicted = time.perf_counter()
        end_peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * rss_scale
        child_peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss * rss_scale
        if args.classifier == "linear_regression":
            assert np.ptp(probabilities[:, 1]) > 1e-6, "Degenerate constant predictions"
            assert np.count_nonzero(model.clf.coef_) > 0, "No fitted coefficients"
        # Recompute via real extractor outside timings to expose exact features.
        train_features = np.array(
            model.feature_extractor.fit(train, use_cache=False, save_cache=False)
        )
        test_features = np.array(
            model.feature_extractor.transform(test, use_cache=False, save_cache=False)
        )
        result = {
            "complete": True,
            "backend": args.backend,
            "classifier": args.classifier,
            "process_peak_rss_before_load_bytes": baseline_peak,
            "process_peak_rss_after_predict_bytes": end_peak,
            "max_child_peak_rss_bytes": child_peak,
            "probability_range": float(np.ptp(probabilities[:, 1])),
            "tfidf": args.tfidf,
            "load_s": loaded - started,
            "fit_s": fitted - loaded,
            "predict_s": predicted - fitted,
            "total_s": predicted - started,
            "train_features_sha256": hashlib.sha256(
                train_features.tobytes()
            ).hexdigest(),
            "test_features_sha256": hashlib.sha256(test_features.tobytes()).hexdigest(),
            "idf_sha256": hashlib.sha256(
                model.feature_extractor.idf.tobytes()
            ).hexdigest(),
            "probabilities": probabilities.tolist(),
            "predictions": (probabilities[:, 1] > 0.5).tolist(),
            "train_shape": list(train_features.shape),
            "test_shape": list(test_features.shape),
        }
        args.output.write_text(json.dumps(result, indent=2) + "\n")


def prepare(source, destination, count):
    import pandas as pd
    from motifboost.repertoire import Repertoire

    metadata = pd.read_csv(source / "metadata.tsv", sep="\t").sort_values("ID")
    # Interleave the two supplied fixture labels, ensuring both train/test classes.
    positive = metadata[metadata.binary_target_1 == "+"]
    negative = metadata[metadata.binary_target_1 != "+"]
    rows = []
    for pos, neg in zip(positive.itertuples(), negative.itertuples()):
        rows.extend((pos, neg))
    used = {row.ID for row in rows}
    rows.extend(row for row in metadata.itertuples() if row.ID not in used)
    rows = rows[:count]
    if len(rows) != count:
        raise ValueError("Requested more examples than bundled fixture contains")
    manifest = []
    for row in rows:
        file = source / "repertoires" / row.ID
        table = pd.read_csv(file, sep="\t")
        repertoire = Repertoire(
            "deeprc-example",
            Path(row.ID).stem,
            {},
            table.amino_acid.tolist(),
            table.templates.tolist(),
        )
        repertoire.save(str(destination))
        manifest.append(
            {
                "id": repertoire.sample_id,
                "label": row.binary_target_1 == "+",
                "source": str(file),
                "source_sha256": sha(file),
                "sequences": len(table),
                "total_weight": int(table.templates.sum()),
            }
        )
    (destination / "samples.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--motifboost", type=Path, required=True)
    parser.add_argument("--deeprc", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--train", type=int, default=80)
    parser.add_argument(
        "--classifier",
        choices=["lightgbm", "linear_regression"],
        default="linear_regression",
    )
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--backend", choices=["upstream", "numpy", "tightarray"])
    parser.add_argument("--tfidf", action="store_true")
    parser.add_argument("--tfidf-mode", choices=["off", "on", "both"], default="off")
    args = parser.parse_args()
    sys.path.insert(0, str(args.motifboost))
    if args.worker:
        worker(args)
        return
    modes = {"off": (False,), "on": (True,), "both": (False, True)}[args.tfidf_mode]
    import numpy as np
    import tightarray, tightarray._core
    import tightarray_immune.motifboost_integration as bridge

    for directory, expected in ((args.motifboost, PIN), (args.deeprc, DEEP_PIN)):
        actual = subprocess.check_output(
            ["git", "-C", str(directory), "rev-parse", "HEAD"], text=True
        ).strip()
        assert actual == expected, (actual, expected)
        assert not subprocess.check_output(
            [
                "git",
                "-C",
                str(directory),
                "status",
                "--porcelain",
                "--untracked-files=no",
            ],
            text=True,
        ).strip()
    guarded = [
        Path(__file__),
        Path(bridge.__file__),
        Path(bridge.__file__).with_name("motifboost.py"),
        Path(bridge.__file__).with_name("sequences.py"),
        Path(tightarray.__file__),
        Path(tightarray._core.__file__),
        *sorted((args.motifboost / "motifboost").rglob("*.py")),
    ]
    before = {str(p): sha(p) for p in guarded}
    with tempfile.TemporaryDirectory(prefix="ta-motif-pipeline-") as temp:
        data = Path(temp)
        preparation_started = time.perf_counter()
        manifest = prepare(
            args.deeprc / "deeprc/datasets/example_dataset", data, args.count
        )
        preparation_seconds = time.perf_counter() - preparation_started
        results = []

        def checkpoint(error=None):
            args.output.write_text(
                json.dumps(
                    {
                        "complete": False,
                        "source_guards": before,
                        "source_pins": {"MotifBoost": PIN, "DeepRC": DEEP_PIN},
                        "dataset": manifest,
                        "classifier": args.classifier,
                        "tsv_to_repertoire_feather_preparation_s": preparation_seconds,
                        "error": error,
                        "rows": results,
                    },
                    indent=2,
                )
                + "\n"
            )

        checkpoint()
        for tfidf in modes:
            for repeat in range(args.repeats):
                policies = ["upstream", "numpy", "tightarray"]
                random.Random(732 + repeat).shuffle(policies)
                for policy in policies:
                    target = data / f"{policy}-{tfidf}-{repeat}.json"
                    command = [
                        sys.executable,
                        str(Path(__file__).resolve()),
                        "--worker",
                        "--classifier",
                        args.classifier,
                        "--motifboost",
                        str(args.motifboost),
                        "--deeprc",
                        str(args.deeprc),
                        "--dataset",
                        str(data),
                        "--train",
                        str(args.train),
                        "--backend",
                        policy,
                        "--output",
                        str(target),
                    ]
                    if tfidf:
                        command.append("--tfidf")
                    log = data / "worker.log"
                    with log.open("w") as stream:
                        run = subprocess.run(
                            command,
                            stdout=stream,
                            stderr=subprocess.STDOUT,
                            timeout=120,
                        )
                    if run.returncode:
                        failure = log.read_text()[-4000:]
                        checkpoint(
                            {
                                "backend": policy,
                                "tfidf": tfidf,
                                "repeat": repeat,
                                "detail": failure,
                            }
                        )
                        raise RuntimeError(failure)
                    row = json.loads(target.read_text())
                    row["repeat"] = repeat
                    results.append(row)
                    checkpoint()
                    print(
                        f"{policy} tfidf={tfidf} repeat={repeat} total={row['total_s']:.3f}s",
                        flush=True,
                    )
        for tfidf in modes:
            selected = [r for r in results if r["tfidf"] == tfidf]
            expected = next(r for r in selected if r["backend"] == "upstream")
            for actual in selected:
                for name in (
                    "train_features_sha256",
                    "test_features_sha256",
                    "idf_sha256",
                    "predictions",
                ):
                    assert actual[name] == expected[name], (actual["backend"], name)
                np.testing.assert_allclose(
                    actual["probabilities"],
                    expected["probabilities"],
                    rtol=0,
                    atol=1e-12,
                )
        assert before == {str(p): sha(p) for p in guarded}, "Measured source changed"
        result = {
            "complete": True,
            "scope": "Real upstream repertoire.load, MotifBoostClassifier.fit and predict_proba; warm imports/JIT, augmentation disabled; upstream classifier selected explicitly, one worker/thread. Fixture demonstration only, not clinical accuracy.",
            "source_pins": {"MotifBoost": PIN, "DeepRC": DEEP_PIN},
            "source_guards": before,
            "python": sys.version,
            "platform": platform.platform(),
            "dependencies": {
                d.metadata["Name"]: d.version
                for d in importlib.metadata.distributions()
            },
            "dataset": manifest,
            "tsv_to_repertoire_feather_preparation_s": preparation_seconds,
            "metadata_sha256": sha(
                args.deeprc / "deeprc/datasets/example_dataset/metadata.tsv"
            ),
            "classifier": args.classifier,
            "memory_scope": "Fresh worker lifetime peak RSS before load and after predict; child maximum separately. These are not incremental allocation or aggregate process-tree RSS; imports and warmup included in high-water marks.",
            "train_samples": args.train,
            "test_samples": args.count - args.train,
            "parity": "Exact feature, IDF and predicted-class equality; probability absolute tolerance1e-12; source guards passed",
            "rows": results,
        }
        args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
