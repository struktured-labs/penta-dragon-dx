"""Issue #18: reject palette-only false positives and preserve runtime bytes."""
import importlib.util
import ast
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from PIL import Image
import yaml

DIAGNOSTICS = Path(__file__).resolve().parents[1] / 'scripts/diagnostics'
with patch.object(sys, 'path', [str(DIAGNOSTICS), *sys.path]):
    spec = importlib.util.spec_from_file_location('verify_gameover_color', DIAGNOSTICS / 'verify_gameover_color.py')
    oracle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(oracle)
    import build_gameover_color as builder
    import verify_death_gameover as death_oracle


class GameOverColorTests(unittest.TestCase):
    def setUp(self):
        self.before = Image.new('RGB', (160, 144), (82, 82, 82))
        self.before.putpixel((30, 32), (173, 173, 173))
        self.before.putpixel((31, 32), (255, 255, 255))
        self.after = self.before.copy()
        self.after.putpixel((30, 32), (255, 132, 255))
        pin = patch.object(oracle, 'GAMEOVER_RGB_SHA256', oracle.digest(self.before.tobytes()))
        pin.start()
        self.addCleanup(pin.stop)

    def test_exact_accent_change_passes(self):
        self.assertEqual(oracle.compare_gameover(self.before, self.after), (True, 1))

    def test_gray_control_fails(self):
        self.assertFalse(oracle.compare_gameover(self.before, self.before)[0])

    def test_missing_glyph_pixel_fails(self):
        self.after.putpixel((31, 32), (82, 82, 82))
        self.assertFalse(oracle.compare_gameover(self.before, self.after)[0])

    def test_extra_colored_pixel_fails(self):
        self.after.putpixel((1, 1), (255, 132, 255))
        self.assertFalse(oracle.compare_gameover(self.before, self.after)[0])

    def test_corruption_shared_by_both_images_fails(self):
        self.before.putpixel((31, 32), (82, 82, 82))
        self.after.putpixel((31, 32), (82, 82, 82))
        with self.assertRaisesRegex(ValueError, 'reviewed intact'):
            oracle.compare_gameover(self.before, self.after)

    def test_wrong_dimensions_fail(self):
        with self.assertRaises(ValueError):
            oracle.compare_gameover(self.before, self.after.resize((320, 288)))

    def test_builder_changes_only_accent_and_global_checksum(self):
        parent = bytearray(b'\xff' * 0x100000)
        parent[builder.ROW:builder.ROW + 8] = builder.OLD
        parent[builder.ROW - 8:builder.ROW] = builder.NEW
        with patch.object(builder, 'PARENT_SHA', builder.digest(parent)):
            result = builder.build(bytes(parent))
        self.assertEqual(len(result), len(parent))
        allowed = {builder.ROW + 4, builder.ROW + 5, 0x14E, 0x14F}
        self.assertTrue(all(a == b or i in allowed for i, (a, b) in enumerate(zip(parent, result))))
        self.assertEqual(result[builder.ROW + 6:builder.ROW + 8], builder.OLD[6:8])
        self.assertEqual(int.from_bytes(result[0x14E:0x150], 'big'),
                         (sum(result[:0x14E]) + sum(result[0x150:])) & 65535)

    def test_central_oracle_selects_only_reviewed_palette_identities(self):
        rom = bytearray(0x40000)
        for row, expected in [(builder.OLD, death_oracle.GAMEOVER_RGB_SHA256),
                              (builder.NEW, death_oracle.GAMEOVER_PURPLE_RGB_SHA256)]:
            rom[builder.ROW:builder.ROW + 8] = row
            self.assertEqual(death_oracle.gameover_rgb_sha256_for_rom(rom), expected)
        rom[builder.ROW] ^= 1
        with self.assertRaises(ValueError):
            death_oracle.gameover_rgb_sha256_for_rom(rom)

    def test_canonical_yaml_compiles_to_tested_palette(self):
        # Execute the actual compiler function without importing build-time
        # environment machinery or creating ROM assets.
        root = DIAGNOSTICS.parents[1]
        source = root / 'scripts/build_v302_title_fix.py'
        tree = ast.parse(source.read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == 'load_death_gameover_text_palette')
        namespace = {'yaml': yaml, 'Path': Path}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
        self.assertEqual(namespace[function.name](root / 'palettes/penta_palettes_v097.yaml'), builder.NEW)


if __name__ == '__main__':
    unittest.main()
