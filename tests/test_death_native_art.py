"""The pose oracle is exact; a copied or shortened lower body cannot pass."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
from death_native_art import exact_native_plane


class NativeDeathArt(unittest.TestCase):
    def test_whole_plane_not_foot_height_or_prefix(self):
        plane = bytes(i % 253 + 2 for i in range(576))
        corpus = {plane}
        self.assertTrue(exact_native_plane(plane, corpus))
        for offset in range(576):
            mutated = bytearray(plane)
            mutated[offset] ^= 1
            self.assertFalse(exact_native_plane(bytes(mutated), corpus))
        self.assertFalse(exact_native_plane(plane[:288] + bytes(288), corpus))
        self.assertFalse(exact_native_plane(plane[:575], corpus))
        self.assertFalse(exact_native_plane(plane + b'\x00', corpus))
        self.assertFalse(exact_native_plane(plane, set()))
