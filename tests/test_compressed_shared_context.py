import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

blosc2 = pytest.importorskip("blosc2")
pytest.importorskip("numpy")

from benchmarks.compressed_shared_context import (
    SharedContextPool,
    independent_compress,
    patched_compression,
)
from tightarray.compressed import CompressedArray


@pytest.mark.parametrize("codec", ["lz4", "zstd"])
def test_exact_bytes_across_lengths_and_prior_output_ownership(codec):
    pool = SharedContextPool(max_contexts=6, max_payload=1024)
    held = []
    for length in (63, 512, 1024, 65, 512, 1024, 2048):
        raw = bytes((index * 19) % 251 for index in range(length))
        for shuffle in (False, True):
            compressed = pool.compress(codec, raw, shuffle)
            assert compressed == independent_compress(codec, raw, shuffle)
            assert blosc2.decompress2(compressed, nthreads=1) == raw
            held.append((compressed, hashlib.sha256(compressed).digest()))
    assert all(hashlib.sha256(data).digest() == digest for data, digest in held)
    info = pool.info()
    assert info["contexts"] <= 6
    assert info["counters"]["capacity_fallback"] > 0
    assert info["counters"]["oversize_fallback"] > 0


def test_busy_key_falls_back_without_blocking_other_keys(monkeypatch):
    pool = SharedContextPool(max_contexts=2)
    entered, release = threading.Event(), threading.Event()
    original = pool._new_context

    def blocked(codec, raw, shuffle):
        if raw[0] == 3:
            entered.set()
            assert release.wait(5)
        return original(codec, raw, shuffle)

    monkeypatch.setattr(pool, "_new_context", blocked)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(pool.compress, "lz4", b"\x03" * 512, False)
        try:
            assert entered.wait(5)
            same = pool.compress("lz4", b"\x04" * 512, False)
            other = pool.compress("lz4", b"\x05" * 1024, False)
            assert blosc2.decompress2(same) == b"\x04" * 512
            assert blosc2.decompress2(other) == b"\x05" * 1024
            assert pool.info()["counters"]["busy_fallback"] == 1
            with pytest.raises(RuntimeError, match="checked-out"):
                pool.clear()
        finally:
            release.set()
        assert blosc2.decompress2(future.result()) == b"\x03" * 512
    assert pool.info()["busy"] == 0


def test_failed_context_is_dropped_and_recreated(monkeypatch):
    pool = SharedContextPool()
    raw = bytes(range(256)) * 2
    pool.compress("zstd", raw, False)
    entry = pool._entries[("zstd", False, len(raw))]

    class FailedUpdate:
        def update_data(self, *args, **kwargs):
            raise RuntimeError("native failure")

    entry.context = FailedUpdate()
    with pytest.raises(RuntimeError, match="native failure"):
        pool.compress("zstd", raw, False)
    assert pool.info()["contexts"] == 0
    assert pool.info()["counters"]["dropped_failure"] == 1
    assert pool.compress("zstd", raw, False) == independent_compress("zstd", raw, False)

    def failed_factory(*args, **kwargs):
        raise RuntimeError("construction failure")

    monkeypatch.setattr(pool, "_new_context", failed_factory)
    with pytest.raises(RuntimeError, match="construction failure"):
        pool.compress("lz4", raw, True)
    assert pool.info()["contexts"] == 1
    assert pool.info()["busy"] == 0


def test_cross_array_concurrency_with_gil_released():
    inputs = [bytes((index + seed) % 32 for index in range(8192)) for seed in range(8)]

    def build(index):
        data = inputs[index]
        codec = "lz4" if index % 2 else "zstd"
        array = CompressedArray(data, chunk_size=4096, cache_bytes=4096, codec=codec)
        array[0] = 255 - index
        array.flush()
        return array._chunks.copy(), array.tobytes()

    expected = [build(index) for index in range(8)]
    pool = SharedContextPool()
    previous = blosc2.set_releasegil(True)
    try:
        with patched_compression(pool), ThreadPoolExecutor(max_workers=4) as executor:
            got = list(executor.map(build, range(8)))
    finally:
        blosc2.set_releasegil(previous)
    assert got == expected
    assert pool.info()["busy"] == 0
    assert pool.info()["contexts"] <= 18
