# Compression wrapper and argument experiment

The [unchanged result artifact](compressed-call-options-results.json) compares
36 configurations: 64/512/4096-byte random, two-label, and run inputs; LZ4/ZSTD;
NOFILTER/BITSHUFFLE. Each policy has 21 randomized-order samples of 128 calls.
All outputs match the public-list baseline byte for byte and decode correctly.
Source guards include the public Python wrapper and native extension binary.

| Policy | Median time / public-list | Range | Faster configurations |
|---|---:|---:|---:|
| Public API, tuple filters and explicit metadata | 1.0003 | 0.9579–1.0172 | 18/36 |
| Internal extension, list filters | 0.9798 | 0.9400–1.0035 | 34/36 |
| Internal extension, tuple filters and explicit metadata | 0.9746 | 0.9387–1.0016 | 35/36 |

Immutable argument containers alone do not give a consistent gain. Bypassing
the public wrapper saves approximately 2–3% at the median in this experiment,
but uses an internal API and has not been measured in the complete array path.
No production policy is changed on this evidence.

Every policy goes through the same Python dispatcher, whose cost is included.
This measures codec calls and result allocation/free, not whole-application
throughput or context reuse. The tuple variant also supplies explicit zero
filter metadata, so this experiment does not isolate tuple allocation alone.
Trials share one process; they are not independent-process replications.

```sh
python -m pytest tests/test_compressed_call_options.py
python -m benchmarks.compressed_call_options --repeats 21 --calls 128 --output results.json
```

Five tests validate both codecs and filters plus source-guard coverage.
