"""Optional real solver integration smoke tests (no generated tables)."""

import pytest

pytest.importorskip("kociemba")
pytest.importorskip("numpy")
from benchmarks.real_rubik import adapt, cases, installed, unpack, verify


def test_storage_adapters_exact():
    original = {"sample": [-1, 0x12, 0x89, 0]}
    expected = bytes([15, 15, 2, 1, 9, 8, 0, 0])
    for policy in (
        "python-original",
        "packed-bytearray",
        "dense-bytearray",
        "numpy-uint8",
        "tightarray4",
    ):
        value = adapt(original, policy)["sample"]
        actual = (
            unpack(value).tobytes()
            if policy in ("python-original", "packed-bytearray")
            else bytes(value)
        )
        assert actual == expected


def test_real_native_solution_and_restore():
    import kociemba

    if not hasattr(kociemba, "lib"):
        pytest.skip("Native backend unavailable")
    from kociemba.pykociemba import coordcube, search

    original = search.getPruning
    table = coordcube.CoordCube.Slice_Flip_Prun
    with pytest.raises(RuntimeError), installed({}, lambda *_: 0):
        raise RuntimeError("restore on failure")
    assert search.getPruning is original
    assert coordcube.CoordCube.Slice_Flip_Prun is table
    case = cases()[0]
    verify(case, kociemba.solve(case["facelets"]))


def test_python_real_solve_parity():
    from pathlib import Path
    import kociemba

    cache = Path(kociemba.__file__).parent / "pykociemba" / "prunetables"
    if len(list(cache.glob("*.pkl"))) != 12:
        pytest.skip("Bundled caches required; never generate tables in tests")
    from kociemba.pykociemba import coordcube, search
    from benchmarks.real_rubik import NAMES, direct

    originals = {n: getattr(coordcube.CoordCube, n) for n in NAMES}
    case = cases()[0]
    expected = search.Search().solution(case["facelets"], 24, 30, False).strip()
    for policy in ("packed-bytearray", "dense-bytearray", "numpy-uint8", "tightarray4"):
        tables = adapt(originals, policy)
        accessor = coordcube.getPruning if policy == "packed-bytearray" else direct
        with installed(tables, accessor):
            solution = search.Search().solution(case["facelets"], 24, 30, False).strip()
            assert solution == expected
            verify(case, solution)
        assert all(getattr(coordcube.CoordCube, n) is originals[n] for n in NAMES)
