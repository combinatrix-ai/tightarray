import numpy as np
import pytest

pytest.importorskip("minigrid")
pytest.importorskip("blosc2")
from benchmarks.real_minigrid_replay import BACKENDS, ENVIRONMENTS, TraceReplay, collect


@pytest.mark.parametrize("env", ENVIRONMENTS)
def test_actual_trace(env):
    images, metadata, missions = collect(env, 131)
    images2, metadata2, missions2 = collect(env, 131)
    np.testing.assert_array_equal(images, images2)
    np.testing.assert_array_equal(metadata, metadata2)
    assert missions == missions2
    assert metadata["truncated"].sum() >= 1
    for i in range(len(images) - 1):
        done = metadata["terminated"][i] or metadata["truncated"][i]
        assert metadata["episode"][i + 1] == metadata["episode"][i] + int(done)
        if not done:
            np.testing.assert_array_equal(images[i, 1], images[i + 1, 0])
    indices = np.array([130, 0, 32, 33, 32, 63, 64])
    for backend in BACKENDS:
        replay = TraceReplay(images, metadata, missions, backend)
        actual, meta, text = replay.sample(indices)
        np.testing.assert_array_equal(actual, images[indices])
        np.testing.assert_array_equal(meta, metadata[indices])
        assert text == missions
        assert replay.sample(np.array([], dtype=np.int64))[0].shape == (0, 2, 7, 7, 3)
        actual[:] = 255
        np.testing.assert_array_equal(replay.sample(indices)[0], images[indices])
        with pytest.raises(IndexError):
            replay.sample(np.array([131]))
