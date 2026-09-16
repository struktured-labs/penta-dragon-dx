import sys
import struct
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
from restart_terrain import terrain


class TerrainControls(unittest.TestCase):
    def fixture(self):
        state = bytearray(0x11800)
        struct.pack_into('<I', state, 0, 0x00400003)
        state[0x340] = 0x93
        state[0x400:0x410] = bytes([0xff, 0] * 8)
        struct.pack_into('<4H', state, 0xd4, 0x7fff, 0x1f, 0x3e0, 0)
        return state

    def test_missing_graphics_rejected(self):
        a = self.fixture(); b = a.copy(); b[0x400:0x410] = bytes(16)
        self.assertNotEqual(terrain(a), terrain(b))

    def test_lost_palette_rejected(self):
        a = self.fixture(); b = a.copy(); b[0xd4:0x114] = bytes(64)
        self.assertNotEqual(terrain(a), terrain(b))

    def test_wrong_graphics_bank_rejected(self):
        a = self.fixture(); b = a.copy(); b[0x3c80] = 8
        self.assertNotEqual(terrain(a), terrain(b))

    def test_priority_loss_rejected(self):
        a = self.fixture(); b = a.copy(); b[0x3c80] = 128
        self.assertNotEqual(terrain(a), terrain(b))

    def test_sprite_movement_does_not_change_background(self):
        a = self.fixture(); b = a.copy(); b[0x260:0x264] = bytes([80, 60, 4, 0])
        self.assertEqual(terrain(a), terrain(b))

    def test_disabled_lcd_not_accepted(self):
        a = self.fixture(); a[0x340] &= 0x7f
        with self.assertRaises(ValueError): terrain(a)

    def test_window_over_terrain_not_accepted(self):
        a = self.fixture(); a[0x340] |= 0x20
        with self.assertRaises(ValueError): terrain(a)
