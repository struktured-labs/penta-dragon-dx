"""#59/#66 sampled low-health Stage7 visible BG attribute consistency.

Not whole-route, tile-pattern, audio, timing, or hardware qualification.
"""
import argparse
import hashlib
import json
from pathlib import Path
from check_boss_prelude_handoff import state
from build_stage7_r274_low_nibble import viewport


def assess(raw, rom):
    if (raw[0x5C80], raw[0x3B7], raw[0x3BA]) != (11, 8, 6):
        raise ValueError('expected low-health Stage7')
    lcd, x, y = raw[0x340], raw[0x343], raw[0x342]
    if not lcd & 0x80 or lcd & 0x20 or x >= 16 or y >= 16:
        raise ValueError('unsupported LCD/window/camera state')
    lut = rom[0x5B600:0x5B700]
    if len(lut) != 256 or not any(lut) or raw[0x4A00:0x4B00] != lut:
        raise ValueError('Stage7 LUT mismatch or blank policy')
    page = 0x400 if lcd & 8 else 0
    bad = []
    cells = viewport(x, y)
    for row, col in sorted(cells):
        cell = page + row * 32 + col
        tile, got = raw[0x1C00+cell], raw[0x3C00+cell]
        if got != lut[tile]:
            bad.append(dict(row=row, col=col, tile=tile, got=got, expected=lut[tile]))
    return dict(passed=not bad, checked_cells=len(cells), mismatches=bad,
                scx=x, scy=y, page=page)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('rom', type=Path)
    p.add_argument('states', nargs='+', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    rom = args.rom.read_bytes()
    checks = [dict(path=str(f), sha256=hashlib.sha256(f.read_bytes()).hexdigest(),
                   **assess(state(f, rom), rom)) for f in args.states]
    result = dict(passed=all(c['passed'] for c in checks), scope=__doc__, checkpoints=checks,
                  rom_sha256=hashlib.sha256(rom).hexdigest(),
                  checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    with args.output.open('x') as out:
        json.dump(result, out, indent=2)
        out.write('\n')
    print(json.dumps(result))
    raise SystemExit(0 if result['passed'] else 1)
