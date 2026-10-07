"""#45: a timing change must not silently turn the return test into gameplay."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
from verify_playtest_boss_handoff import return_checkpoint_frame


class ReturnCheckpoint(unittest.TestCase):
    def rows(self, shift=0):
        rows = []
        for n in range(1, 501 + shift):
            stage, scene = ('00', '18') if n < 30 else ('00', '02')
            if 80 <= n < 300 + shift:
                stage, scene = '07', '09'
            if 300 + shift <= n < 400 + shift:
                stage, scene = '00', '18'
            rows.append(dict(frame=str(n), stage=stage, scene=scene))
        return rows

    def test_observed_boundary_not_a_fixed_frame(self):
        for shift in (-60, 0, 80):
            available = set(range(1, 501 + shift, 30))
            frame, boundary = return_checkpoint_frame(self.rows(shift), available)
            self.assertEqual(boundary, 400 + shift)
            self.assertLess(frame, boundary)
            self.assertLessEqual(boundary - frame, 30)

    def test_post_return_checkpoint_is_not_accepted(self):
        with self.assertRaisesRegex(ValueError, 'no pre-return'):
            return_checkpoint_frame(self.rows(), {401, 450})

    def test_boot_card_cannot_substitute_for_secret_return(self):
        rows = self.rows()[:70]
        with self.assertRaisesRegex(ValueError, 'one observed'):
            return_checkpoint_frame(rows, {1, 20})

    def test_short_window_is_rejected_not_truncated(self):
        with self.assertRaisesRegex(ValueError, 'complete initialization'):
            return_checkpoint_frame(self.rows(), {300}, replay_frames=100)

    def test_missing_trace_frame_fails(self):
        rows = self.rows()
        del rows[300]
        with self.assertRaisesRegex(ValueError, 'missing or unordered'):
            return_checkpoint_frame(rows, {360})

    def test_multiple_returns_are_ambiguous(self):
        rows = self.rows()
        rows[449]['scene'] = '18'
        with self.assertRaisesRegex(ValueError, 'one observed'):
            return_checkpoint_frame(rows, {360, 450})


if __name__ == '__main__':
    unittest.main()
