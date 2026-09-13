# Bio application pilots

Six local, output-equivalent experiments on macOS arm64 / CPython 3.12.8 (September 2026). These are selected real application methods, **not full application or model-training benchmarks**. The strongest opportunities are removing string conversions in MotifBoost and unnecessary label generation in immuneML. Neither large speedup establishes a packing-specific benefit.

| Measured operation | Original ms | Candidate ms | Original / candidate |
| --- | ---: | ---: | ---: |
| BioNumPy: unique DNA 21-mer counts | 7.445 | 7.592 | 0.98x |
| immuneML: AA 3-mer labels and repertoire CSR counts | 256.424 | 4.345 | 59.02x |
| MotifBoost: resident packed repertoire to weighted normalized trigrams | 10.119 | 0.271 | 37.38x |
| Scirpy: symmetric Hamming cutoff-2 API, including per-call JIT/setup | 303.121 | 1.929 | 157.16x* |
| DeepRC: resident sample extraction, all 100 example repertoires | 7.915 | 8.384 | 0.94x |
| CompAIRR: exact repertoire overlap, CLI versus in-process adapter | 8.808 | 7.267 | 1.21x* |

Medians pool ten samples from two separate processes per backend. Each process warms once, times five calls, and checks a digest after each call. Imports and input preparation are outside timed calls unless described below. The second pass reverses project/backend order; final DeepRC runs both use baseline then candidate. Raw samples, versions, payload sizes, process RSS, allocation peaks and hashes are in [results](results). All paired output digests match, including the NumPy ablations. Timing is exploratory, not a statistical confidence interval or CI performance gate.

## MotifBoost: promising feature extraction, not a training speedup

On 1,550 TCR sequences, the original `PackedStringArray.get_all_strs()` plus actual `ngram_features` takes 10.119 ms, versus 0.271 ms for the packed numeric adapter. Boundary symbols, feature order, weighted counts and normalization match exactly. Weights cycle through 1..5 and are synthetic; sequences come from Scirpy's fixture.

An additional test starts from ordinary Python strings, as `ngram_features` normally accepts. Including encoding and packing on every candidate call, the original takes **6.548 ms versus 0.523 ms (12.53x)**. This is one process/five timed samples per backend. The resident comparison is a distinct usage mode, not the default string-input baseline.

A NumPy uint8 version of the same numeric pipeline takes **0.319 ms** (one process/five samples). Most of the gain comes from eliminating strings and intermediate small arrays. The original already packs its storage efficiently: retained data plus indices is **26,460 bytes**, versus **40,800 bytes** for our packed adapter and **50,395 bytes** for the NumPy adapter. Our extra boundaries and two index arrays make it larger than MotifBoost's original packed representation. Classifier training, augmentation, hyperparameter search and multiprocessing were not measured. The next useful experiment is integrating numeric feature extraction into actual training preprocessing and measuring the whole run.

## Interpretation of the other pilots

- **immuneML:** Uses actual `encode_continuous_kmer` and `KmerFrequencyVectorizer.fit_transform`, with eight deterministic repertoire partitions. The original enumerates the entire 21^3 label vocabulary through repeated string conversion/alphabet construction. Generating only observed labels removes that overhead. Keeping BioNumPy's original k-mer kernel with the new label path takes **4.739 ms**, so packing is not necessary for most of this 59x improvement. No model training, normalization changes or complete immuneML pipeline are claimed.
- **BioNumPy:** The existing k-mer implementation is already competitive. This includes pack/rolling-code generation and unique counting, but excludes FASTQ reading and initial alphabet encoding. All 1,000 reads (217,598 bases) in the public fixture are ACGT-only. No demonstrated speedup.
- **Scirpy:** The installed API constructs an inner Numba function per call. The 157x API result includes that repeated setup/JIT cost. Capturing and reusing its compiled inner function gives a **2.949 ms** median, excluding input encoding and CSR assembly; this has different boundaries from the 1.929 ms candidate API. It rules out interpreting 157x as native-kernel acceleration. One compiled-kernel sample suffered a 246 ms scheduling outlier; all raw samples are retained. The candidate matches both the installed API and the source checkout's supplied `hamming_WU3k_csr_result.npz` exactly (1,550 x 1,550, 2,090 nonzero entries). Only unnormalized symmetric Hamming with a cutoff is implemented, not rectangular comparisons or other metrics. Dense intermediate matrices limit scaling.
- **DeepRC:** Calls the actual resident `get_sample` on all 100 included example repertoires (2,806 sequences); the adapter preserves returned values, shapes and counts. Constructor/metadata loading, disk dataset conversion, random sampling and GPU training are bypassed. Sequence payload falls from **53,314 to 33,328 bytes (37.5%)**, while unpacking makes extraction slightly slower. Length/count storage is shared and excluded from those payload totals. This tiny fixture does not establish an application RSS saving.
- **CompAIRR:** Runs the actual single-thread C++ CLI in exact overlap mode ignoring gene columns. The adapter matches its 8 x 8 count-product matrix for 3,100 derived rows. Baseline includes CLI launch and output parsing; the Python candidate runs in-process. **The 1.21x ratio is not evidence of beating CompAIRR's native algorithm.** Approximate matching, indels, larger cohorts and full CLI parity are untested. CompAIRR remains an important strong baseline.

## Memory and timing boundaries

`retained_payload_bytes` / `retained_sequence_bytes` count the specified backing buffers, not full Python objects. `worker_peak_rss_bytes` is macOS process high-water RSS after warmup/timed calls, including imports, JIT and setup. `child_peak_rss_bytes` is recorded separately for the CompAIRR subprocess. These are not directly comparable standalone CompAIRR/Python memory measurements. A separate `tracemalloc` call records allocation peak after RSS measurement; its time is excluded. It does not capture every native allocation. In particular, reduced Numba compilation can change RSS without any packed-storage benefit.

## Reproduction

Use a separate local experiment directory. No upstream source modifications or pushes are needed. Baseline packages are **BioNumPy 1.0.14 and Scirpy 0.25.1 from PyPI**; their source checkouts provide fixtures. immuneML, DeepRC and MotifBoost are imported directly from the pinned checkouts. CompAIRR is built from source. Exact source URLs/revisions are in [sources.json](results/sources.json); input SHA-256 and package versions are in each result. The lock records this macOS Python 3.12 environment, not a universal cross-platform dependency promise.

```sh
export BIO_PILOT_ROOT="$(mktemp -d)"
export MPLCONFIGDIR="$BIO_PILOT_ROOT/mpl"
export NUMBA_NUM_THREADS=1
export MLFLOW_DISABLE_AGENT_HINT=1
python3.12 -m venv "$BIO_PILOT_ROOT/venv"
. "$BIO_PILOT_ROOT/venv/bin/activate"
pip install -r benchmarks/bio/requirements-lock.txt
pip install -e .
python - <<'PY'
import json, os, subprocess
from pathlib import Path
root = Path(os.environ['BIO_PILOT_ROOT']) / 'repos'
root.mkdir()
for name, source in json.loads(Path('benchmarks/bio/results/sources.json').read_text()).items():
    target = root / name
    subprocess.run(['git', 'clone', source['url'], str(target)], check=True)
    subprocess.run(['git', '-C', str(target), 'checkout', '--detach', source['revision']], check=True)
    subprocess.run(['git', '-C', str(target), 'remote', 'set-url', '--push', 'origin', 'DISABLED'], check=True)
PY
make -C "$BIO_PILOT_ROOT/repos/compairr"
pytest -q benchmarks/bio/test_adapters.py
for project in bionumpy immuneml motifboost scirpy deeprc compairr; do
  for backend in baseline candidate; do
    python benchmarks/bio/run.py "$project" "$backend" "$BIO_PILOT_ROOT/$project-$backend.json"
  done
done
python benchmarks/bio/run.py motifboost_ingest baseline "$BIO_PILOT_ROOT/motifboost-ingest-original.json"
python benchmarks/bio/run.py motifboost_ingest candidate "$BIO_PILOT_ROOT/motifboost-ingest-packed.json"
python benchmarks/bio/run.py immuneml numpy "$BIO_PILOT_ROOT/immuneml-numpy.json"
python benchmarks/bio/run.py motifboost numpy "$BIO_PILOT_ROOT/motifboost-numpy.json"
python benchmarks/bio/scirpy_compiled.py
python benchmarks/bio/verify_results.py
```

The adapters use private, experimental `_rolling_codes` and `_hamming_rows` methods. They assume ASCII fixture alphabets, positive supported k and valid weights; they are not drop-in upstream releases. Rolling codes use least-significant-symbol-first radix encoding and native uint64 byte order (little-endian on the measured arm64 Mac). Hamming stores distance+1, reserving zero for values beyond cutoff, in a dense uint8 matrix. No biology-specific alphabet is built into tightarray itself.

Validation: tightarray's 456 tests, strict type checks, and all 456 tests under ASan/UBSan passed; three independent adapter tests passed. The pinned Array API suite passed 1,385 tests with one existing expected failure. Source archive contents and a secret scan were also checked. Scirpy's supplied sparse reference and all saved baseline/candidate digests match. No upstream application was published or modified.
