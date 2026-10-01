"""#18 color/geometry evidence after secret-area projectile death."""
import csv
import hashlib
import mmap
from pathlib import Path
import sys
import unittest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
from verify_death_gameover import gameover_rgb_sha256_for_rom
from verify_gameover_color import compare_gameover


class SecretDeathGameOver(unittest.TestCase):
    def test_full_scene_retains_transition_and_checks_every_settled_frame(self):
        base = ROOT / 'tmp/secret-alias-chunk-lowhealth-return-01'
        video = Path('/mnt/data/tmp/penta-secret-alias-chunk-lowhealth-return-01-av/native.video')
        gray = ROOT / 'tmp/gameover-color-parent-sequence-01/gameover-1.png'
        if not all(p.exists() for p in (base / 'receipt.json', video, gray)):
            self.skipTest('local emulator evidence unavailable')
        rom = (base / 'candidate.gb').read_bytes()
        self.assertEqual(hashlib.sha256(rom).hexdigest(), '2b797a6af30598141d874a8a272e9a7c77012044fe82f649f1b3e9142d31f306')
        expected = gameover_rgb_sha256_for_rom(rom)
        with (base / 'trace.tsv').open() as stream:
            rows = list(csv.DictReader(stream, delimiter='\t'))
        self.assertEqual(video.stat().st_size, len(rows) * 92160)
        matched, transitions = [], []
        with Image.open(gray) as original, video.open('rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as frames:
            self.assertFalse(compare_gameover(original, original)[0])
            for row in rows:
                if row['scene'] != '17': continue
                frame = int(row['frame'])
                image = Image.frombytes('RGBA', (160, 144), frames[(frame - 1) * 92160:frame * 92160]).convert('RGB')
                if hashlib.sha256(image.tobytes()).hexdigest() == expected:
                    self.assertTrue(compare_gameover(original, image)[0])
                    matched.append(frame)
                else:
                    transitions.append(frame)
        self.assertEqual(matched, list(range(1084, 1300)))
        self.assertEqual(transitions, list(range(1041, 1084)))


if __name__ == '__main__': unittest.main()
