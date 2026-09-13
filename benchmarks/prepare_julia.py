"""Write the same 1-bit input and gather indices used by competitors.py."""
from pathlib import Path
import random
import sys

root = Path(sys.argv[1])
root.mkdir(parents=True, exist_ok=True)
rng = random.Random(982 + 1 + 65536)
(root / 'julia-input.bin').write_bytes(bytes(rng.randrange(2) for _ in range(65536)))
(root / 'julia-indices.txt').write_text('\n'.join(str(rng.randrange(65536)) for _ in range(256)))
