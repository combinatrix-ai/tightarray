# Bounded codec destination: rejected exact-pruning hypothesis

The installed Blosc2 4.13.1 public `compress2` allocates input length plus maximum overhead. Its private `SChunk._prefilter_data` accepts a caller-sized mutable destination and calls `blosc2_compress_ctx` with that limit. This experiment asks whether a candidate could safely be rejected when that bounded call reports no fit.

**The required equivalence fails.** All 1,176 full-destination SChunk outputs match independent `compress2` outputs exactly, before and after bounded calls. Among 4,704 bounded trials, ZSTD reports 674 false negatives: 337 at the known full-output size and another 337 with one extra byte. Successful bounded outputs are byte-identical to the full baseline; failure is the problem. No LZ4 false negatives were observed in this finite matrix, which is not a proof for arbitrary inputs/settings.

A concrete ZSTD/NOFILTER counterexample is `bytes(17) + b"\xff" + bytes(46)`: 64 logical bytes compress to 61 bytes with the normal full destination. Fresh length-matched SChunk context output agrees, but destinations of 61 and 62 bytes both report `The result could not fit `. The subsequent full destination still reproduces the baseline. A pinned-version regression test preserves this counterexample.

The matrix includes seven distributions (random 256/8/32-state, period31, runs, two high labels, sparse spikes), eighteen logical lengths from 63 to 16,385 around byte/word/chunk boundaries, direct/raw/palette candidate payloads, both codecs, and both filters. Each candidate uses its own ephemeral length-matched SChunk, seeded with the source as in the earlier context study. It is discarded after the full/bounded/full probes; no global or per-array pool persists. The oracle is untimed and makes no RSS or speed claim.

Each probe uses a writable bytearray destination with a sentinel tail and verifies successful decompression. Only the exact no-fit RuntimeError text is classified as no fit; other errors remain errors. Besides full-size−1/equal/+1 bounds, the experiment tests candidate bounds derived from the existing no-codec structural winner and sequential full-compression candidate results, subtracting palette bytes and preserving equality. Nonpositive bounds are clamped to one solely to exercise the private API; real selection should skip such calls.

Of the 508 unexpected-error trials, all are undersized winner-bound probes. Their capacities range from 4 to 31 bytes, including values above the public 16-byte minimum. This private context path therefore needs an appropriate 32-byte header boundary, rather than blindly using the public minimum; it must not treat generic internal compression errors as normal no-fit results. The 674 exact-size/+1 false negatives occur independently of these invalid small destinations, so correcting the header check does not rescue the equivalence hypothesis.

The observed sequential winner-bound trials themselves contain no false negatives in this dataset. However, 149 candidates using production filter choices and compressing to less than their input length fail the independent exact-size boundary check. Thus the proposed general rule—“a no-fit bounded call proves the ordinary encoded candidate cannot fit”—is not valid. The finite winning-bound results do not establish that it is safe for future data or tighter incumbents. Production compression remains unchanged.

[Full oracle records](compressed-destination-bound-results.json) preserve input specifications, compressed hashes, capacities, errors, filter choices, exactness flags, and dependency/source hashes. Run:

```sh
python -m benchmarks.compressed_destination_bound --output docs/compressed-destination-bound-results.json
```
