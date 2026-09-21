"""Lossless palette eligibility audit of bundled pygame-ce example assets.
No image content is copied to the repository; only numeric measurements.
"""

import hashlib
import json
import os
from pathlib import Path

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import numpy as np
import pygame
from PIL import Image

from tightarray import Array

NAMES = [
    "alien1.gif",
    "alien2.gif",
    "alien3.gif",
    "player1.gif",
    "bomb.gif",
    "shot.gif",
    "explosion1.gif",
    "background.gif",
    "brick.png",
    "city.png",
]


def audit():
    root = Path(pygame.__file__).parent / "examples" / "data"
    rows = []
    for name in NAMES:
        path = root / name
        rgba = np.asarray(Image.open(path).convert("RGBA"))
        palette, indices = np.unique(rgba.reshape(-1, 4), axis=0, return_inverse=True)
        bits = max(1, (len(palette) - 1).bit_length())
        packed = Array(indices.astype(np.uint8), bits=bits)
        decoded = palette[np.frombuffer(packed.tobytes(), dtype=np.uint8)].reshape(
            rgba.shape
        )
        np.testing.assert_array_equal(decoded, rgba)
        rows.append(
            {
                "asset": name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "shape": list(rgba.shape),
                "colors": len(palette),
                "bits": bits,
                "rgba_bytes": rgba.nbytes,
                "uint8_palette_bytes": indices.size + palette.nbytes,
                "packed_palette_bytes": packed.nbytes + palette.nbytes,
                "source_file_bytes": path.stat().st_size,
            }
        )
    return {
        "pygame": pygame.version.ver,
        "source": "pygame-ce installed wheel examples/data; no quantization",
        "scope": "representation sizes only, not RSS, decode timing or engine E2E",
        "records": rows,
    }


if __name__ == "__main__":
    Path("docs/results/real-sprite-audit.json").write_text(
        json.dumps(audit(), indent=2) + "\n"
    )
