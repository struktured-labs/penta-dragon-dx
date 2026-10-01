"""#20: retain a negative reproduction, not a red-bleed release clearance."""
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from build_v301_gdma import _bg_table


def unexpected_red_cells(state, table):
    # BG plane sample only, including cells that the window/sprites may cover.
    # An exact raster assertion would require scanline-time data as well.
    base = 0x1c00 if state[0x340]&8 else 0x1800
    bad = []
    for row in range(18):
        for col in range(20):
            off = base + (((state[0x342]//8)+row)&31)*32 + (((state[0x343]//8)+col)&31)
            tile, attr = state[0x400+off], state[0x2400+off]&7
            if attr == 1 and table[tile]&7 != 1:
                bad.append((off,tile))
    return bad


class MinibossRedPaletteEvidence(unittest.TestCase):
    def test_full_retained_boss_capture_has_stable_cram_and_no_unexpected_bg1(self):
        table = _bg_table()
        for name,digest,count,frames in (
                ('gargoyle-reported-patrol-corrected-01',
                 '63fc2863a842c884d3af5615037a2f68c0207565a2ecd237eacd8db443c99779',1826,2400),
                ('gargoyle-latest-patrol-01',
                 'a5251b015485073f7856e9b6dccd6218c148383731956b0913a9087b64bc8651',1744,2400),
                ('gargoyle-reported-long-menu-01',
                 '7c23b65c2b666bf2661e3007c1e2c6478e58795c677c570393a1df2f2efc0bfe',3506,4080)):
            path = Path('/mnt/data/tmp')/f'penta-{name}-av/native.states'
            if not path.exists(): self.skipTest('local native capture unavailable')
            raw = path.read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),digest)
            self.assertEqual(len(raw),frames*71680)
            palettes,checked = set(),0
            for offset in range(0,len(raw),71680):
                state = raw[offset:offset+71680]
                if state[0x3bf] != 1: continue
                checked += 1
                palettes.add(state[0xd4:0x114])
                self.assertEqual(unexpected_red_cells(state,table),[],(name,offset//71680+1))
            self.assertEqual(checked,count)
            self.assertEqual(len(palettes),1)

    def test_long_menu_was_observed_and_pre_stimulus_state_matches(self):
        root = Path('/mnt/data/tmp')
        long_path = root/'penta-gargoyle-reported-long-menu-01-av/native.states'
        short_path = root/'penta-gargoyle-reported-patrol-corrected-01-av/native.states'
        if not long_path.exists() or not short_path.exists():
            self.skipTest('local native captures unavailable')
        raw = long_path.read_bytes()
        self.assertEqual(raw[:1350*71680],short_path.read_bytes()[:1350*71680])
        visible = [i+1 for i in range(4080) if raw[i*71680+0x340]&32]
        self.assertEqual(visible,list(range(1355,3091)))
        self.assertFalse(raw[3119*71680+0x340]&32)

    def test_deliberate_red_floor_attribute_is_detected(self):
        table = _bg_table()
        tile = next(i for i,palette in enumerate(table) if palette&7 != 1)
        state = bytearray(71680)
        state[0x1c00] = tile
        state[0x3c00] = 1
        self.assertIn((0x1800,tile),unexpected_red_cells(state,table))


if __name__ == '__main__': unittest.main()
