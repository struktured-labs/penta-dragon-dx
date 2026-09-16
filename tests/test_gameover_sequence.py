import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
import gameover_sequence as sequence


class SequenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'tmp')
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)
        for cycle in (0, 1, 2):
            for age in (60, 61):
                Image.new('RGB', (160, 144), (45, 90, 150)).save(
                    self.out / f'sequence-title-{cycle}-{age:04d}.png')
        self.ages = patch.object(sequence, 'TITLE_AGES', range(60, 62))
        self.ages.start(); self.addCleanup(self.ages.stop)
        self.gameover = patch.object(sequence, 'GAMEOVER_AGES', ())
        self.gameover.start(); self.addCleanup(self.gameover.stop)

    def test_all_matching_frames(self):
        self.assertEqual(sequence.validate_sequence(self.out)['title_frame_pairs'], 4)

    def test_single_bad_frame_is_not_hidden_by_later_recovery(self):
        Image.new('RGB', (160, 144), 'gray').save(self.out / 'sequence-title-1-0060.png')
        with self.assertRaisesRegex(ValueError, 'rendering changed'):
            sequence.validate_sequence(self.out)

    def test_missing_frame_rejected(self):
        (self.out / 'sequence-title-2-0061.png').unlink()
        with self.assertRaises(FileNotFoundError):
            sequence.validate_sequence(self.out)

    def test_corrupt_gameover_frame_rejected(self):
        with patch.object(sequence, 'GAMEOVER_AGES', (10,)):
            Image.new('RGB', (160, 144), 'white').save(self.out / 'sequence-gameover-1-0010.png')
            with self.assertRaisesRegex(ValueError, 'Game Over sequence corrupted'):
                sequence.validate_sequence(self.out)

    def test_missing_gameover_frame_rejected(self):
        with patch.object(sequence, 'GAMEOVER_AGES', (10,)):
            with self.assertRaises(FileNotFoundError):
                sequence.validate_sequence(self.out)
