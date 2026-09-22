# MotifBoost application integration

The optional bridge connects tightarray-immune to the **actual MotifBoost feature extractor, classifier training, and prediction path**, with an explicit backend choice. The pinned external application is `hmirin/MotifBoost@0fd515b787cd0834c02becefc772bc6059247d5a`. No upstream code is copied into the package, and its obsolete dependency pins are not silently installed.

```python
from motifboost.methods.motif import MotifBoostClassifier
from tightarray_immune.motifboost_integration import motifboost_backend

# Repertoire objects use MotifBoost's ordinary load/preprocessing API.
with motifboost_backend("tightarray"):
    model = MotifBoostClassifier(
        n_jobs=1,
        classifier_method="linear_regression",  # upstream's logistic regression name
        augmentation_times=0,
        tfidf_mode=False,
    )
    model.fit(train_repertoires, train_labels)
    probabilities = model.predict_proba(test_repertoires)
    predicted_labels = probabilities[:, 1] > 0.5
```

Use `motifboost_backend("upstream")` to retain the original numeric/Numba implementation. Enter the selected context for every feature-generating operation, including later predictions. The upstream module function is restored on normal exit and exceptions. Its fork workers inherit the selection. This is a **process-global, opt-in context**, not a concurrent backend registry: nested contexts raise and concurrent thread use is unsupported. The bridge does not mutate an installed source file or require a private fork.

The feature order, boundary symbols, per-k normalization and integer count weights use the existing packaged `MotifRepertoire` adapter. Upstream fit, transformation, TFIDF, cache handling, and classifier code stay in place. In particular, upstream applies TFIDF in transform but returns untransformed arrays from fit; this behavior is preserved rather than corrected in this experiment. Its non-Optuna `predict()` recursively calls itself, so the integration deliberately uses the working `predict_proba()` and an explicit probability threshold. The unrelated upstream estimator `repr()` also fails on missing constructor attributes; no workaround is injected.

Supported tightarray configurations require distinct ASCII alphabet symbols, a single distinct ASCII boundary symbol absent from input sequences, known input symbols, nonnegative integer weights, weighted positions <=2**53, `1 <= start < stop <=64`, and total dense feature dimensions <=1,000,000. The default amino-acid trigrams are supported; the default alphabet's 5-grams exceed the cap and raise. There is no silent fallback for unsupported upstream configurations. NumPy is a **benchmark-private ablation**, not a supported public integration backend.

## Actual data and execution boundary

The pipeline uses all 100 bundled example repertoire TSVs from `ml-jku/DeepRC@108d08d8cf2d2d69eb3f6caef1aa04d624dec871`: 2,806 sequences and the supplied `binary_target_1` metadata (58 positive, 42 negative). These are upstream example fixtures; this study makes no biological accuracy or clinical performance claim. Sorted positive/negative IDs are interleaved, remaining positives appended, then split into 80 training and 20 test repertoires. The split is for deterministic integration validation, not a scientific evaluation design.

TSV ingestion and `Repertoire.save()` create the application's real Feather/pickle representation once, outside each measured pipeline. The first measured preparation took 2.05 seconds. Each fresh worker then runs actual `Repertoire.load()` on all 100 samples, `MotifBoostClassifier.fit()`, and `predict_proba()`. Imports and one original Numba-kernel warmup occur before timing for every backend. Augmentation is disabled, the upstream feature pool has one process, and numerical thread counts are one. Feature extraction still uses the application's own fork pool. This is warmed application execution, not cold installation/JIT time.

Full train/test feature matrices and IDF arrays are recomputed through the actual extractor after each timed prediction, then checked for byte-identical equality. Predicted classes match exactly and probabilities use absolute tolerance1e-12 (zero relative tolerance). Source/package/native-extension guards before and after the run must match. Backend order rotates deterministically across fresh-process repetitions.

## Final logistic regression pipeline

The supported upstream `classifier_method="linear_regression"` actually constructs scikit-learn's `LogisticRegression`. With TFIDF **off**, all nine fresh-process pipelines completed (three repetitions per backend), fitted nonzero coefficients, and produced nonconstant predictions. Train/test feature matrices and IDFs matched exactly, predicted classes matched, and probabilities agreed within absolute1e-12. The held-out probability range was only0.000175: this proves a nonconstant trained model was exercised, not useful predictive accuracy.

| Backend | Load ms | Fit ms | Predict ms | Total ms | Individual total times ms |
|---|---:|---:|---:|---:|---|
| upstream | 82.9 | 65.1 | 25.4 | 194.2 | 194.2,209.8,161.6 |
| tightarray | 70.1 | 48.1 | 19.2 | 136.2 | 261.4,136.2,133.2 |
| NumPy ablation | 116.7 | 115.8 | 34.9 | 274.0 | 274.0,370.1,224.6 |

These are within-classifier comparisons, not ratios chained from the earlier LightGBM experiment. Median fit improved1.35×, prediction1.32×, and whole pipeline1.43×. With only three repetitions, overlapping total-time ranges, and unrelated load-time variance, the whole-pipeline ratio is **exploratory**, not a promised speedup. The first tightarray repetition was slower than every upstream repetition. The separate TSV-to-MotifBoost-file preparation took4.93s this run and is excluded from the table; a single job starting from TSV therefore sees a much smaller overall benefit.

Fresh worker process lifetime peak RSS (median, MiB):

| Backend | Before load | After prediction | Maximum child peak, separate |
|---|---:|---:|---:|
| upstream | 333.47 | 350.77 | 21.73 |
| tightarray | 333.50 | 350.34 | 23.30 |
| NumPy ablation | 333.33 | 350.84 | 22.48 |

There is **no demonstrated whole-process RAM reduction**. These high-water marks include imports and equal Numba warmup; subtracting them does not measure incremental allocation. Child peaks are reported separately and must not be added to the parent peak as if they were simultaneous independent allocations. The bridge still retains upstream repertoire strings and dense feature matrices; its packed sequence storage is temporary during feature construction. A compact temporary representation alone cannot establish an application memory win.

[Final logistic raw results](bio-motifboost-pipeline-logistic-results.json) include process peaks, every sample, source guards, versions, prediction ranges, and per-stage timings. They measure the committed integration and benchmark logic after the public NumPy backend was removed and strict input validation was corrected. Final optional integration checks: **4 passed** (actual weighted/unweighted TFIDF extractor parity, custom alphabet/boundary, actual classifier fit/predict, restoration/nesting, invalid inputs); module `mypy --strict` passed.

## Initial default LightGBM result: limited by this fixture

Five repetitions for each backend and TFIDF setting produced these median times:

| TFIDF | Backend | Load ms | Fit ms | Predict ms | Total ms |
|---|---|---:|---:|---:|---:|
| off | upstream | 72.6 | 73.9 | 21.5 | 175.3 |
| off | tightarray | 72.7 | 65.8 | 21.1 | 157.6 |
| off | NumPy ablation | 78.3 | 103.5 | 32.6 | 215.5 |
| on | upstream | 83.4 | 75.1 | 26.1 | 186.0 |
| on | tightarray | 76.6 | 65.6 | 21.1 | 160.4 |
| on | NumPy ablation | 75.2 | 106.4 | 33.6 | 215.1 |

The actual default 100-tree LightGBM training and prediction APIs ran successfully, but all test probabilities were constant on this small fixture. These numbers are therefore retained as an integration/correctness result, **not evidence of faster useful model training**. The apparent 1.11–1.16× whole-pipeline speedup also includes load-time variance. Component medians need not sum to the median total.

[Unchanged initial raw results](bio-motifboost-pipeline-results.json) contain all samples, supplied labels, feature/IDF hashes, probabilities, pins, dependency versions, and source hashes. After this measurement the unchanged NumPy algorithm moved to the benchmark as a private ablation and public backend selection narrowed to `upstream`/`tightarray`; the measured pre-refactor files were retained at `/tmp/ta-motifboost-pipeline-measured.py` and `/tmp/ta-motifboost-integration-measured.py`. Historical hashes were not rewritten.

## Reproduce

The [portable pipeline](../benchmarks/bio/motifboost_pipeline.py) and [optional bridge](../packages/tightarray-immune/src/tightarray_immune/motifboost_integration.py) are the durable integration, not a patch that exists only in a temporary clone. Clone the pinned upstream repositories, and put MotifBoost and the two local package sources on `PYTHONPATH`. Current minimal import dependencies used here are NumPy, Numba, pandas, scikit-learn, SciPy, LightGBM, optuna-integration with LightGBM, matplotlib, mlflow-skinny, bitarray, pyarrow, cloudpickle, joblib and tqdm. Exact installed versions are recorded in the result artifacts. The historical MotifBoost setup pins old immuneML/h5py/SciPy versions; those unused dependencies are not required by this selected pipeline.

```sh
export PYTHONPATH=/path/to/MotifBoost:/path/to/tightarray:/path/to/tightarray/packages/tightarray-immune/src
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
export MPLCONFIGDIR=/tmp/motif-matplotlib XDG_CACHE_HOME=/tmp/motif-cache
export MLFLOW_DISABLE_AGENT_HINT=1
python benchmarks/bio/motifboost_pipeline.py \
  --motifboost /path/to/MotifBoost --deeprc /path/to/DeepRC \
  --classifier linear_regression --tfidf-mode off --repeats 3 \
  --output docs/bio-motifboost-pipeline-logistic-results.json
```

The bridge itself has no dependency on NumPy's ablation implementation, LightGBM selection, fixture paths, or benchmark code. MotifBoost is imported lazily when the context is entered. Optional real-application tests skip if that external package is absent.

## Upstream TFIDF limitation found during logistic validation

A follow-up using the application's supported logistic regression classifier successfully produced varying predictions with TFIDF disabled. With TFIDF enabled, a held-out motif absent from every training repertoire receives infinite IDF; upstream clears NaNs but leaves these infinities. Scikit-learn then raises `ValueError: Input X contains infinity or a value too large for dtype('float64')`. The first follow-up stopped on this condition after nine TFIDF-off runs, before writing its final artifact. Those partial timings are not used as evidence. The bridge does not silently clean these values or alter upstream feature semantics. The follow-up benchmark now checkpoints completed rows durably and offers `--tfidf-mode off|on|both`; this fixture's logistic end-to-end result is intentionally limited to TFIDF-off, while exact TFIDF parity is still checked with the original LightGBM path and extractor tests.

After the original LightGBM measurement, the bridge also stopped coercing weights to int64 before validation. This prevents fractional weights from being silently truncated and large unsigned weights from wrapping. The fixture's valid uint16 weights retain identical features. The new logistic artifact measures this validated final bridge version, and neither the original raw samples nor their hashes were rewritten.

