import random
import pytest
from tightarray import Array


def encode(values, bits):
    lanes = 64 // bits
    return b''.join(sum(v << (j * bits) for j, v in enumerate(values[i:i+lanes])).to_bytes(8, 'big')
                    for i in range(0, len(values), lanes))


@pytest.mark.parametrize('bits', range(1, 9))
def test_word_codec_padding_and_mutation(bits):
    rng = random.Random(bits)
    lanes = 64 // bits
    for n in [0, 1, lanes-1, lanes, lanes+1, 63, 64, 65, 127, 4096]:
        raw = rng.randbytes(((n+lanes-1)//lanes)*8)
        expected = [(int.from_bytes(raw[i//lanes*8:i//lanes*8+8], 'big') >> ((i%lanes)*bits)) & ((1<<bits)-1) for i in range(n)]
        a, padding = Array._from_word_bytes(raw, n, bits)
        assert a.tolist() == expected
        assert a.sum() == sum(expected)
        assert a.count(0) == expected.count(0)
        assert a.equals(Array(expected, bits=bits, layout='word-aligned'))
        assert a._to_word_bytes(padding) == raw
        assert a._to_word_bytes(None) == encode(expected, bits)
        if n:
            a[n-1] = 0
            expected[n-1] = 0
            clean = encode(expected, bits)
            padded = bytes(x | y for x, y in zip(clean, padding or bytes(len(clean))))
            assert a._to_word_bytes(padding) == padded
        for layout in ['packed', 'word-aligned']:
            b = Array(expected, bits=bits, layout=layout)
            for start in range(min(n, 70)):
                assert b[start:]._to_word_bytes(None) == encode(expected[start:], bits)


def test_word_codec_validation():
    for raw, n, bits in [(b'', -1, 1), (b'', 0, 0), (b'', 0, 9), (b'', 1, 1), (bytes(8), 0, 1)]:
        with pytest.raises(ValueError):
            Array._from_word_bytes(raw, n, bits)
    a, padding = Array._from_word_bytes(bytes(8), 1, 1)
    assert padding is None
    for p in [b'', bytes(16), 1]:
        with pytest.raises(ValueError):
            a._to_word_bytes(p)
