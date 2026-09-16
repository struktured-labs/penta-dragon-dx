import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
import build_restore_room03_scanner_r437 as builder


class RestoreRoom03Scanner(unittest.TestCase):
    def test_scope_and_tail_entry(self):
        source = builder.BASE.read_bytes()
        result = builder.build(source)
        allowed = set(range(builder.SITE, builder.SITE + len(builder.OLD))) | {0x14D,0x14E,0x14F}
        self.assertTrue(all(i in allowed for i,(a,b) in enumerate(zip(source,result)) if a != b))
        self.assertEqual(result[builder.SITE:builder.SITE+len(builder.NEW)], builder.NEW)
        with self.assertRaises(ValueError):
            builder.build(source + b'mutation')
