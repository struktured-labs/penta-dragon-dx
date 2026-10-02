"""#14 experimental allocation guards; not rendered or lifecycle acceptance."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/diagnostics/build_sara_doorway_priority.py'
spec = importlib.util.spec_from_file_location('doorway_builder', SOURCE)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class DoorwayBuilderTests(unittest.TestCase):
    def test_source07_preserves_projectile_and_continue_repairs(self):
        path = SOURCE.parents[2] / 'tmp/stream-regressions-source-07/candidate.gb'
        if not path.exists():
            self.skipTest('local source07 candidate unavailable')
        parent = path.read_bytes()
        result = builder.build(parent, combined=True)
        self.assertEqual(builder.digest(result),
                         'f7896dee8620a85ca3e1a9596647968557cf3fa8f4cee58a9b10189ebaad0898')
        allowed = {0x14E, 0x14F, *range(0x50C1, 0x50CC),
                   *range(33*0x4000, 35*0x4000)}
        for bank in (13, 16):
            allowed.update(range(bank*0x4000+0x3B42, bank*0x4000+0x3B48))
            allowed.update(range(bank*0x4000+0x3CBF,
                                 bank*0x4000+0x3CBF+len(builder.OLD_COPY)))
        self.assertTrue(all(a == b or i in allowed
                            for i, (a, b) in enumerate(zip(parent, result))))
        self.assertEqual(result[35*0x4000:36*0x4000], parent[35*0x4000:36*0x4000])
        self.assertEqual(result[32*0x4000:33*0x4000], parent[32*0x4000:33*0x4000])

    def parent(self):
        rom = bytearray(b'\xff' * 0x100000)
        rom[0x1188:0x118B] = bytes.fromhex('CBBFC9')
        rom[0x50C1:0x50CC] = bytes.fromhex('28063E0100001803AF0000')
        for bank in (13, 16):
            off = bank*0x4000 + 0x3CBF
            rom[off:off+len(builder.OLD_COPY)] = builder.OLD_COPY
            rom[bank*0x4000+0x3B45:bank*0x4000+0x3B48] = bytes.fromhex('CD8811')
            rom[bank*0x4000+0x3B42:bank*0x4000+0x3B45] = bytes.fromhex('CDA211')
        return bytes(rom)

    def build(self, rom):
        with patch.object(builder, 'PARENT_SHA', builder.digest(rom)):
            return builder.build(rom)

    def test_wrong_parent_rejected(self):
        with self.assertRaisesRegex(ValueError, 'exact'):
            builder.build(self.parent())

    def test_extension_bank_must_be_wholly_unused(self):
        for bank in (33, 34):
            rom = bytearray(self.parent())
            rom[bank*0x4000+500] = 0
            with self.assertRaisesRegex(ValueError, 'wholly unused'):
                self.build(bytes(rom))

    def test_changed_bytes_bounded_and_palette_tables_untouched(self):
        parent = self.parent()
        result = self.build(parent)
        allowed = {0x14E, 0x14F, *range(0x1188, 0x118B), *range(0x50C1, 0x50CC),
                   *range(33*0x4000, 35*0x4000)}
        for bank in (13, 16):
            off = bank*0x4000+0x3CBF
            allowed.update(range(off, off+54))
            self.assertEqual(result[bank*0x4000+0x3000:bank*0x4000+0x3A00],
                             parent[bank*0x4000+0x3000:bank*0x4000+0x3A00])
        self.assertEqual(len(parent), len(result))
        self.assertTrue(all(a == b or i in allowed for i, (a,b) in enumerate(zip(parent,result))))
        self.assertEqual(int.from_bytes(result[0x14E:0x150], 'big'),
                         (sum(result[:0x14E])+sum(result[0x150:])) & 65535)

    def test_helper_does_not_read_dx_map_selector_directly(self):
        code = builder.helper()
        self.assertIn(bytes.fromhex('FE02'), code)
        self.assertIn(bytes.fromhex('FA70DB'), code)
        self.assertLessEqual(0xDB40+len(code), 0xDB70)
        self.assertNotIn(bytes.fromhex('F0C4'), code)

    def test_unexpected_priority_caller_rejected(self):
        rom = bytearray(self.parent())
        rom[0x2000:0x2003] = bytes.fromhex('CD8811')
        with self.assertRaisesRegex(ValueError, 'callers changed'):
            self.build(bytes(rom))

    def test_combined_helper_preserves_flash_and_avoids_stage4_payload(self):
        code = builder.helper(combined=True)
        native_flash_prefix = bytes.fromhex('E5F57BCB3FCB3FE0DDC6C06F26AB7EA728073D77F1CBE71803F1CBA7')
        self.assertTrue(code.startswith(native_flash_prefix))
        self.assertIn(bytes.fromhex('FA3EDB'), code)
        self.assertLessEqual(0xDB40+len(code), 0xDB7F)
        rom = self.parent()
        with patch.object(builder, 'PARENT_SHA', builder.digest(rom)):
            result = builder.build(rom, combined=True)
        self.assertEqual(result[0x1188:0x118B], bytes.fromhex('CBBFC9'))
        for bank in (13, 16):
            off = bank*0x4000+0x3B42
            self.assertEqual(result[off:off+6], bytes.fromhex('CD40DB000000'))
        # Stage-4's source DB00..DB3D payload is untouched.
        self.assertEqual(result[22*0x4000+0x2300:22*0x4000+0x233E],
                         rom[22*0x4000+0x2300:22*0x4000+0x233E])

    def test_scratch_b_changes_only_attribute_save_and_two_restores(self):
        old = builder.helper(combined=True)
        new = builder.helper(combined=True, scratch_b=True)
        self.assertEqual(len(old), len(new))
        changes = [(a,b) for a,b in zip(old,new) if a != b]
        self.assertEqual(changes, [(0xF5,0x47),(0xF1,0x78),(0xF1,0x78)])
        with self.assertRaisesRegex(ValueError, 'requires combined'):
            builder.helper(scratch_b=True)


if __name__ == '__main__':
    unittest.main()
