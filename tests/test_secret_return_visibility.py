"""#45 reject exposed initialization, missing evidence and permanent blanking."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
from check_secret_return_visibility import assess


class SecretReturnVisibility(unittest.TestCase):
    def frames(self):
        frames = []
        for n in range(1, 72):
            raw = bytearray(71680)
            raw[0x5C80] = 24 if n == 1 else 2
            raw[0x340] = 0x83
            raw[0x3C1] = int(n == 71)
            if 2 <= n <= 6:
                raw[0x1C00] = 1
            frames.append((n, raw, n <= 10))
        return frames

    def test_hidden_map_then_visible_complete_gameplay(self):
        self.assertEqual(assess(self.frames())['hidden_unfinished_frames'], 5)

    def test_one_exposed_corrupt_cell_fails(self):
        frames = self.frames()
        n, raw, _ = frames[3]
        frames[3] = (n, raw, False)
        with self.assertRaisesRegex(ValueError, 'unfinished map is visible'):
            assess(frames)

    def test_wrong_selected_page_fails(self):
        frames = self.frames()
        frames[20][1][0x340] |= 8
        frames[20][1][0x2000] = 1
        with self.assertRaisesRegex(ValueError, 'unfinished map is visible'):
            assess(frames)

    def test_missing_truncated_or_wrong_route_fails(self):
        for change in ('missing','truncated','scene','boundary','inactive'):
            with self.subTest(change=change):
                frames = self.frames()
                if change == 'missing': del frames[20]
                if change == 'truncated': frames.pop()
                if change == 'scene': frames[20][1][0x5C80] = 9
                if change == 'boundary': frames[0][1][0x5C80] = 0
                if change == 'inactive': frames[-1][1][0x3C1] = 0
                with self.assertRaises(ValueError): assess(frames)

    def test_permanent_blank_screen_fails(self):
        with self.assertRaisesRegex(ValueError, 'permanent blanking'):
            assess([(n, raw, True) for n, raw, _ in self.frames()])


if __name__ == '__main__': unittest.main()
