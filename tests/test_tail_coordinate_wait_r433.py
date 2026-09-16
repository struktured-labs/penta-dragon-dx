import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
import build_tail_coordinate_wait_r433 as builder


class TailGuardTest(unittest.TestCase):
    def test_scope_and_dead_flags(self):
        source = builder.BASE.read_bytes()
        result = builder.build(source)
        self.assertEqual(result[0x4284:0x4289], bytes.fromhex('3E 1D C3 47 08'))
        allowed = set(range(0x4284,0x4295)) | set(range(builder.OFFSET,builder.OFFSET+len(builder.CODE))) | {0x14D,0x14E,0x14F}
        self.assertTrue(all(i in allowed for i,(a,b) in enumerate(zip(source,result)) if a != b))
        mutation = bytearray(source)
        mutation[0x437E] = 0x1A  # RR D would consume the supposedly dead carry.
        with self.assertRaises(AssertionError):
            builder.check_callers(mutation)
