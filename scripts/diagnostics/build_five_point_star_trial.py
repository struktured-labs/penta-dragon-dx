"""Issue #22: experimental data-only five-point-star recolor, not release qualification."""
import argparse
import hashlib
import json
from pathlib import Path

PARENT = '4731248ad2d28f56539197ddfa38fcb8f79713832b7997905647caf35d34f903'
TILES = (0x82, 0x83, 0x92, 0x93)
ART_SHA = 'd7156afbb1e8f9a310c0a1283a7fe16e4fca38839057d24ad3e966771c3aba6d'


def build(parent):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact Ted-menu-reinstall parent required')
    art = b''.join(parent[0x1F000+t*16:0x1F010+t*16] for t in TILES)
    if hashlib.sha256(art).hexdigest() != ART_SHA:
        raise ValueError('five-point-star source art differs')
    result = bytearray(parent)
    for tile in TILES:
        if parent[0x37000+tile] != 0:
            raise ValueError('star no longer uses the neutral dungeon palette')
        result[0x37000+tile] = 5
    # Original index0 includes both the upper star interior and white space
    # outside its square. Only the interior is recolored. Lower star shading
    # already uses index1. Black outlines and every nonzero pixel are retained.
    # BG5 supplies the established gold/red power-up treatment; its red square
    # backdrop is a visual choice requiring review, not a neutral-background claim.
    for y in range(1, 15):
        for x in range(1, 15):
            tile = TILES[(y//8)*2+x//8]
            off = 0x1F000+tile*16+(y%8)*2
            bit = 1 << (7-x%8)
            if not ((parent[off] | parent[off+1]) & bit):
                result[off] |= bit
    result[0x14E:0x150] = ((sum(result[:0x14E])+sum(result[0x150:])) & 65535).to_bytes(2, 'big')
    return bytes(result)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    if a.output.exists() or (root/'tmp').resolve() not in a.output.resolve().parents:
        p.error('fresh repository tmp directory required')
    result = build(a.parent.read_bytes())
    a.output.mkdir(parents=True)
    (a.output/'candidate.gb').write_bytes(result)
    receipt = dict(issue=22, experimental=True, release_qualified=False,
        parent_sha256=PARENT, candidate_sha256=hashlib.sha256(result).hexdigest(),
        builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='four source CHR tiles and four dungeon LUT entries; no executable changes')
    (a.output/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt))
