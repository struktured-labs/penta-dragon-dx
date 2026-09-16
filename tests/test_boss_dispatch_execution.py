import contextlib
import io
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'scripts/diagnostics')]
from boss_dispatch_execution import walk
from verify_boss_atomic_attr_contract import verify


class BossDispatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / 'tmp/arena-palette-storage-r455/candidate.gb'
        if not path.exists():
            raise unittest.SkipTest('local immutable candidate unavailable')
        cls.rom = path.read_bytes()

    def test_source_contract_and_all_nine_actual_routes(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(verify(self.rom), 0)
        for scene in range(0x0C, 0x15):
            target, trace = walk(self.rom, scene)
            self.assertEqual(target, 0xDA60 if scene == 0x0E else 0xDBA4)
            self.assertGreater(len(trace), 80)

    def test_actual_execution_rejects_bank_discriminator_mapper_stack_corruption(self):
        for address, value in ((0x14, 30), (0x19, 0x3D), (0x09C0, 0),
                               (31*16384+0x2D53, 0xDB)):
            changed = bytearray(self.rom)
            self.assertNotEqual(changed[address], value)
            changed[address] = value
            with self.subTest(address=hex(address)), self.assertRaises(AssertionError):
                walk(changed, 0x0C)


if __name__ == '__main__':
    unittest.main()
