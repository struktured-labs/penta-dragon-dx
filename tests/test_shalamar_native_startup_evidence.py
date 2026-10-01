"""#43: retained full captures, not general sound-fidelity qualification."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class ShalamarStartupEvidence(unittest.TestCase):
    def test_full_capture_invariant_under_host_startup_delay(self):
        receipts = []
        for suffix in ('02', '03'):
            run = ROOT / 'tmp' / f'shalamar-gated-native-menu-{suffix}'
            receipt = json.loads((run / 'completion.json').read_text())
            self.assertTrue(receipt['completed'])
            self.assertEqual(receipt['rom']['sha256'],
                '126dd0b7fff1e03eb6b224f818b85398593c7109ffb676cc538c1bd90742304b')
            for key in ('rom', 'state', 'probe', 'runner', 'native_tap'):
                self.assertEqual(digest(Path(receipt[key]['path'])),
                                 receipt[key]['sha256'])
            capture = receipt['native_capture']
            self.assertEqual(capture['restored_replay_epoch']['status'], 'PASS')
            self.assertEqual(capture['metadata']['frames'], 1080)
            self.assertEqual(capture['metadata']['samples'], 2370048)
            for name, expected in capture['hashes'].items():
                self.assertEqual(digest(Path(receipt['av_output']) / name), expected)
            verification = json.loads((run / 'verification.json').read_text())
            self.assertEqual(verification['status'], 'PASS')
            self.assertEqual(verification['native_capture_failures'], [])
            receipts.append(receipt)
        for key in ('rom', 'state', 'probe', 'runner', 'runtime', 'native_tap',
                    'select_presses', 'held_frames', 'third_entry_hold', 'audio_options'):
            self.assertEqual(receipts[0][key], receipts[1][key], key)
        # No trimming, normalization, alignment, or excluded frames/samples.
        self.assertEqual(receipts[0]['native_capture']['hashes'],
                         receipts[1]['native_capture']['hashes'])


if __name__ == '__main__':
    unittest.main()
