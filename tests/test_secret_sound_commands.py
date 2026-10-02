import csv
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
from check_secret_sound_commands import check


class SecretSoundCommandsTests(unittest.TestCase):
    def rows(self):
        return [dict(event=event, command='26', active='00', cycle=str(i))
                for i, event in enumerate(('request', 'read', 'accept'))]

    def test_native_and_phantom_negative_control(self):
        rows = self.rows()
        self.assertFalse(check(rows)['errors'])
        rows[1]['command'] = 'FF'
        self.assertTrue(check(rows)['errors'])

    def test_wrong_priority_empty_and_truncation_fail(self):
        rows = self.rows()
        rows[2]['event'] = 'reject'
        self.assertTrue(check(rows)['errors'])
        self.assertTrue(check([])['errors'])
        self.assertTrue(check(self.rows()[:-1])['errors'])

    def test_overwritten_request_is_reported(self):
        rows = self.rows()
        rows.insert(0, dict(rows[0], command='18'))
        result = check(rows)
        self.assertFalse(result['errors'])
        self.assertEqual(result['overwritten_requests'][0]['command'], '18')

    def test_retained_complete_controls(self):
        for name, sha, overwritten in (
            ('parent', '5d1c002ab468679de12f9a6dac7f7a231e83b240a82f79298531f00eee0353e4', 5),
            ('trial03', '391856e838a246ac6255e0fca11f832a18a8f10a8284218037e5cfa56c016afa', 10),
            ('original', 'ed5909757f40663653c07fceeb351bb3102f886ec38fe7db1af3e6a3479f2cfc', 2),
        ):
            with self.subTest(name=name):
                path = ROOT / f'tmp/secret-sound-commands-{name}-01/sound-commands.tsv'
                if not path.exists():
                    self.skipTest('local diagnostic traces unavailable')
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), sha)
                with path.open() as stream:
                    result = check(csv.DictReader(stream, delimiter='\t'))
                self.assertFalse(result['errors'])
                self.assertEqual(len(result['overwritten_requests']), overwritten)
