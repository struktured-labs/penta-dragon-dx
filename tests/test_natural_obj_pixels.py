from pathlib import Path
import sys
import unittest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import check_natural_obj_pixels as oracle


class ObjPixelsTests(unittest.TestCase):
    def setUp(self):
        self.data = bytearray(4326)
        self.data[-6] = 0x82
        self.data[4160:4164] = bytes([16,8,0,0])
        self.data[0] = 0x80  # One nontransparent pixel at (0,0).
        self.data[4098:4100] = bytes([31,0])  # Color 1: red.

    def test_one_pixel_and_transparent_background(self):
        im = Image.new('RGB', (160,144), (0,255,0))
        im.putpixel((0,0), (255,0,0))
        self.assertEqual(oracle.compare_image(self.data, im)[:2], (1,0))
        im.putpixel((0,0), (0,255,0))
        self.assertEqual(oracle.compare_image(self.data, im)[:2], (1,1))

    def test_flips_and_8x16_odd_tile(self):
        self.data[-6] |= 4
        self.data[4162:4164] = bytes([1,0x60])
        self.assertEqual(list(oracle.expected_pixels(self.data)), [(7,15,0,(255,0,0))])

    def test_oam_order_and_transparency(self):
        self.data[4164:4168] = bytes([16,8,1,0])
        self.data[16:18] = bytes([0,0xC0])  # Blue color 2 in slot 1.
        self.data[4100:4102] = bytes([0,0x7C])
        self.assertEqual(list(oracle.expected_pixels(self.data)),
                         [(0,0,0,(255,0,0)), (1,0,1,(0,0,255))])

    def test_offscreen_x_still_uses_scanline_slot(self):
        for slot in range(10):
            self.data[4160+4*slot:4164+4*slot] = bytes([16,0,0,0])
        self.data[4200:4204] = bytes([16,8,0,0])
        self.assertEqual(list(oracle.expected_pixels(self.data)), [])

    def test_behind_bg_sprite_still_occludes_lower_oam(self):
        self.data[4163] = 128
        self.data[4164:4168] = bytes([16,8,0,0])
        self.assertEqual(list(oracle.expected_pixels(self.data)), [])

    def test_disabled_sprites_and_resized_image_rejected(self):
        with self.assertRaisesRegex(ValueError, 'non-native'):
            oracle.compare_image(self.data, Image.new('RGB',(320,288)))
        self.data[-6] = 0x80
        with self.assertRaisesRegex(ValueError, 'disabled'):
            list(oracle.expected_pixels(self.data))


if __name__ == '__main__':
    unittest.main()
