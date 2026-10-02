"""#22 narrow, exact-fixture rendered-star gate; not whole-game qualification."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image
from verify_pickup_class_palettes import serialized_state

PARENT = '4731248ad2d28f56539197ddfa38fcb8f79713832b7997905647caf35d34f903'
TRIAL = 'd744124d3d161247e0584bb39e8db1243ade4e428cbc15f82a85c10d0a4ac4d5'


def inspect(reference, candidate):
    a = Image.open(reference/'frame-1500.png').convert('RGB')
    b = Image.open(candidate/'frame-1500.png').convert('RGB')
    s = serialized_state(reference/'frame-1500.ss0')
    t = serialized_state(candidate/'frame-1500.ss0')
    changed = [(x, y) for y in range(144) for x in range(160)
               if a.getpixel((x, y)) != b.getpixel((x, y))]
    wram_changed = [i for i in range(0x4400, 0xC400) if s[i] != t[i]]
    # At camera1192,624, this map tile is screen72,80. Three interior points
    # avoid the red square backdrop and black outline. Color is pinned to BG5.
    points = [(80, 84), (80, 86), (79, 87)]
    gold = lambda rgb: rgb[0] >= 240 and rgb[1] >= 180 and rgb[2] < 80
    checks = {
        'parent_pin': hashlib.sha256((reference/'candidate.gb').read_bytes()).hexdigest() == PARENT,
        'trial_pin': hashlib.sha256((candidate/'candidate.gb').read_bytes()).hexdigest() == TRIAL,
        'star_center_gold': all(gold(b.getpixel(p)) for p in points),
        'broken_center_not_gold': all(not gold(a.getpixel(p)) for p in points),
        'pixel_difference_confined_to_star': len(changed) == 152 and all(72 <= x < 88 and 80 <= y < 96 for x, y in changed),
        'same_clock': s[0x198:0x1A0] == t[0x198:0x1A0],
        'same_oam': s[0x260:0x300] == t[0x260:0x300],
        'only_expected_wram_palette_changes': set(wram_changed) == {0x4A82,0x4A83,0x4A92,0x4A93,0x754A,0x754B,0x756A,0x756B}
            and all(s[i] == 0 and t[i] == 5 for i in wram_changed),
    }
    return dict(status='PASS' if all(checks.values()) else 'FAIL', checks=checks,
                changed_pixels=len(changed), changed_wram_offsets=wram_changed,
                center_rgb=[b.getpixel(p) for p in points],
                scope='cold boot, one position assist, frame1500 only; no audio/menu/collection/hardware qualification')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('reference', type=Path)
    p.add_argument('candidate', type=Path)
    a = p.parse_args()
    result = inspect(a.reference, a.candidate)
    print(json.dumps(result, indent=2))
    raise SystemExit(result['status'] != 'PASS')
