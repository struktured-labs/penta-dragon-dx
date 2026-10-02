from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_semantic_buffer_redirect_r393 as builder


class SemanticBufferTests(unittest.TestCase):
    def test_writer_matrix_and_fixed_bank_dispatch(self):
        code = builder.writer()
        self.assertEqual(builder.static_checks(code)['cases'], 480)
        proof = builder.stub_checks(builder.stub()[:7], code)
        self.assertEqual(proof['bank_on_return'], 19)
        self.assertEqual(proof['sp_delta'], 0)

    def test_direct_mapper_call_from_banked_rom_is_rejected(self):
        bad = bytes([0x3E, builder.NEW_BANK, 0xCD, 0x61, 0,
                     0xCD, builder.NEW_ADDR & 255, builder.NEW_ADDR >> 8,
                     0x3E, 19, 0xCD, 0x61, 0, 0xAF, 0xC9])
        with self.assertRaises(AssertionError):
            builder.stub_checks(bad, builder.writer())

    def test_missing_completed_page_mask_is_rejected(self):
        code = builder.writer().replace(bytes.fromhex('E6 FC'), bytes.fromhex('E6 FF'), 1)
        with self.assertRaises(AssertionError):
            builder.static_checks(code)

    def test_page_domain_restored_across_low_byte_wrap(self):
        for page in (0x98, 0x9C):
            result = builder.run_writer(builder.writer(), ff01=1, page=page,
                                        h=page+1, l=255, e=6, c=2)
            self.assertEqual(result['stores'], [(0xD1FF,6,3,0),(0xD200,6,3,0)])
            self.assertEqual((result['H'],result['L'],result['C']), (page+2,1,0))


if __name__ == '__main__':
    unittest.main()
