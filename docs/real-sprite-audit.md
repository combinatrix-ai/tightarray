# Actual game sprite eligibility audit

Ten assets bundled with pygame-ce2.5.8 were losslessly mapped to an RGBA palette.
No quantization was used; alpha participates in color identity. All decoded
RGBA bytes match the original Pillow decode. Only measurements/hashes are
stored in this repository, not copied image assets. Source: installed pygame-ce
`examples/data` (https://github.com/pygame-community/pygame-ce/tree/main/examples/data).

| Asset | Colors | Bits | uint8 indices + palette | Packed + palette | Original encoded file |
|---|---:|---:|---:|---:|---:|
| alien1.gif | 223 | 8 | 6572 B | 6572 B | 3826 B |
| alien2.gif | 222 | 8 | 6568 B | 6568 B | 3834 B |
| alien3.gif | 220 | 8 | 6560 B | 6560 B | 3829 B |
| player1.gif | 176 | 8 | 6194 B | 6200 B | 3470 B |
| bomb.gif | 231 | 8 | 1308 B | 1308 B | 1170 B |
| shot.gif | 9 | 4 | 198 B | 124 B | 129 B |
| explosion1.gif | 234 | 8 | 9036 B | 9040 B | 6513 B |
| background.gif | 233 | 8 | 61412 B | 61412 B | 9133 B |
| brick.png | 2 | 1 | 64261 B | 8040 B | 170 B |
| city.png | 2 | 1 | 584 B | 80 B | 143 B |

Seven of ten assets need8bits even after lossless palette remapping, so
narrow packing does not reduce their index plane. Three have fewer colors,
but the largest such asset is an almost constant two-color texture: encoded
PNG storage exploits that structure. This is a rejection of these particular
assets as a compelling narrow-width application, not a general conclusion
about pixel art. Indexed rendering or quantizing colors would be different
changes, and the decoded RGBA→palette benefit belongs to palette encoding.

Figures are representation sizes only, not RSS, decode timings or game-engine
E2E. Palette storage is included; Python objects and container metadata are
excluded except whatever is present in the original image files.

Reproduce with installed pygame-ce==2.5.8 and Pillow:

```sh
python -m benchmarks.real_sprite_audit
python -m pytest -q tests/test_real_sprite_audit.py
```
