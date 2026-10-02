from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from verify_stage1_natural_menu_bg import native_stage1_enemy_quads, enemy_quad_signatures


class NativeAnimation(unittest.TestCase):
    def test_rom_authority_and_mutations(self):
        rom=(ROOT/'tmp/title-nightfall-port/r443e3f2-v6-r445c/candidate.gb').read_bytes()
        quads=native_stage1_enemy_quads(rom)
        self.assertEqual(len(quads),20)
        for start, end in ((0x650B, 0x658B), (0x664B, 0x66CB)):
            for offset in range(start, end):
                bad=bytearray(rom);bad[offset]^=1
                with self.assertRaises(ValueError): native_stage1_enemy_quads(bad)
        for quad in quads:
            objects=[dict(slot=12+n,x=75+dx,y=14+dy,tile=t,flags=f)
                     for n,(dx,dy,t,f) in enumerate(quad)]
            self.assertEqual(enemy_quad_signatures(dict(height=8,oam_objects=objects))[12],quad)
            for field,value in (('x',76),('tile','10'),('flags','84'),('flags','07')):
                altered=[dict(o) for o in objects];altered[0][field]=value
                self.assertFalse(set(enemy_quad_signatures(dict(height=8,oam_objects=altered)).values()) & quads)
            self.assertFalse(enemy_quad_signatures(dict(height=16,oam_objects=objects)))

    def test_wraparound_geometry_remains_a_complete_quad(self):
        objects = [
            dict(slot=8 + n, x=x, y=y, tile=tile, flags='25')
            for n, (x, y, tile) in enumerate((
                (247, 65, '69'), (-1, 65, '68'),
                (247, 73, '6B'), (-1, 73, '6A'),
            ))
        ]
        signature = enemy_quad_signatures(
            dict(height=8, oam_objects=objects)
        )[8]
        rom=(ROOT/'tmp/title-nightfall-port/r443e3f2-v6-r445c/candidate.gb').read_bytes()
        self.assertIn(signature, native_stage1_enemy_quads(rom))

    def test_sequential_vertical_update_boundary_is_narrow(self):
        rom=(ROOT/'tmp/title-nightfall-port/r443e3f2-v6-r445c/candidate.gb').read_bytes()
        quads = native_stage1_enemy_quads(rom)
        for bottom_y in (7, 8, 9):
            objects = [
                dict(slot=16 + n, x=x, y=y, tile=tile, flags='24')
                for n, (x, y, tile) in enumerate((
                    (20, 31, '51'), (28, 31, '50'),
                    (20, 31 + bottom_y, '53'),
                    (28, 31 + bottom_y, '52'),
                ))
            ]
            signature = enemy_quad_signatures(
                dict(height=8, oam_objects=objects)
            )[16]
            self.assertIn(signature, quads)
        for bottom_y in (6, 10):
            objects[2]['y'] = 31 + bottom_y
            objects[3]['y'] = 31 + bottom_y
            self.assertFalse(enemy_quad_signatures(
                dict(height=8, oam_objects=objects)
            ))
        objects[2]['y'] = 39
        objects[3]['y'] = 40
        self.assertFalse(enemy_quad_signatures(
            dict(height=8, oam_objects=objects)
        ))
