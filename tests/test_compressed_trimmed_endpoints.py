import random

import pytest

pytest.importorskip("blosc2")

from benchmarks.compressed_trimmed_endpoints import (
    candidate_size,
    endpoint_class,
    extra_cases,
)
from benchmarks.compressed_trimmed_policy import pinned_baseline


def brute_best(raw, palette):
    sizes = []
    for value in range(256):
        marker = bytes([value])
        start = len(raw) - len(raw.lstrip(marker))
        stop = len(raw.rstrip(marker))
        if start < stop:
            sizes.append(candidate_size(raw, start, stop, palette))
    return min(sizes)


@pytest.mark.parametrize("palette", [False, True])
def test_best_endpoint_matches_all_default_values(palette):
    rng = random.Random(993)
    with pinned_baseline() as (base, _):
        cls = endpoint_class(base)
        for _ in range(50):
            alphabet = rng.sample(range(256), rng.randrange(2, 9))
            raw = bytes([rng.choice(alphabet)]) * rng.randrange(1, 40)
            raw += bytes(rng.choice(alphabet) for _ in range(rng.randrange(1, 80)))
            raw += bytes([rng.choice(alphabet)]) * rng.randrange(1, 40)
            original = base(raw, palette=palette)._chunks[0]
            result = cls(raw, palette=palette)
            if isinstance(original, int):
                assert result._chunks[0] == original
            else:
                assert len(result._chunks[0]) == min(
                    len(original), brute_best(raw, palette)
                )
            assert result.tobytes() == raw


@pytest.mark.parametrize("codec", ["none", "zstd"])
def test_endpoint_cases_and_mutations(codec):
    with pinned_baseline() as (base, _):
        cls = endpoint_class(base)
        for name, data in extra_cases(4096):
            raw = data.tobytes()
            obj = cls(raw, codec=codec, cache_bytes=512)
            assert obj.tobytes() == raw, name
            assert obj[::-7] == raw[::-7]
            expected = bytearray(raw)
            for index in (0, 767, 768, 1023, 1024, 3583, 3584, 4095):
                obj[index] = 17
                expected[index] = 17
            obj.flush()
            obj.clear_cache()
            assert obj.tobytes() == bytes(expected), name


def test_shorter_edge_can_win_due_to_palette():
    raw = bytes([0]) * 96 + bytes([0, 1, 2, 3]) * 48 + bytes([255]) * 64
    with pinned_baseline() as (base, _):
        obj = endpoint_class(base)(raw)
        chunk = obj._chunks[0]
        assert chunk[0] == 0
        assert chunk[2] == 255
        assert obj.tobytes() == raw
