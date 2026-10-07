"""#54 placement/preimage guards; real CPU contract has a separate verifier."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('headers',ROOT/'scripts/diagnostics/build_clean_stage_headers.py')
headers=importlib.util.module_from_spec(spec)
spec.loader.exec_module(headers)


class HeaderPlacement(unittest.TestCase):
    def setUp(self):
        parent=bytearray([255])*0x100000
        parent[0x7B91:0x7BA1]=headers.LOADER
        parent[0x7BA1:0x7CB8]=bytes((i*17)&255 for i in range(0x117))
        parent[0x7BA1:0x7BB3]=bytes.fromhex('6f2600295d54291929291919d711b37b19c9')
        parent[0x61:0x67]=bytes.fromhex('EA09DCC3BE09')
        parent[0x9BE:0x9C4]=bytes.fromhex('E099EA0021C9')
        original=bytearray(parent[:0x40000])
        for start in (0x7C91,0x7CAE):
            original[start:start+9]=bytes(9)
        self.parent=bytes(parent)
        self.original=bytes(original)

    def build(self,parent=None):
        parent=self.parent if parent is None else bytes(parent)
        with patch.object(headers,'PARENT',headers.sha(parent)):
            return headers.build(parent,self.original)

    def test_clean_mirror_and_live_helpers_retained(self):
        result=self.build()
        self.assertEqual(result[headers.offset(0x4800):headers.offset(0x4905)],self.original[0x7BB3:0x7CB8])
        self.assertEqual(result[0x7BB3:0x7C7E],self.original[0x7BB3:0x7C7E])
        for start in (0x7C91,0x7CAE):
            self.assertEqual(result[start:start+9],self.parent[start:start+9])
        self.assertEqual(len(result),len(self.parent))

    def test_switch_landing_addresses(self):
        result=self.build()
        self.assertEqual(result[0x7B91:0x7BB3],headers.COMMON)
        self.assertEqual(result[0x7C7E:0x7C84],bytes.fromhex('F53E3FCD6100'))
        self.assertEqual(result[headers.offset(0x7C81):headers.offset(0x7C87)],bytes.fromhex('CD6100C30040'))
        self.assertEqual(result[0x7C84:0x7C86],bytes.fromhex('F1C9'))

    def test_occupied_expansion_bank_rejected(self):
        data=bytearray(self.parent); data[headers.offset(0x6100)]=0
        with self.assertRaisesRegex(ValueError,'unused expansion'):
            self.build(data)

    def test_unexpected_header_change_rejected(self):
        data=bytearray(self.parent); data[0x7BB3]^=1
        with self.assertRaisesRegex(ValueError,'stage-header difference'):
            self.build(data)

    def test_unknown_parent_rejected(self):
        with self.assertRaisesRegex(ValueError,'exact played parent'):
            headers.build(self.parent,self.original)

    def test_global_checksum_excludes_stored_checksum(self):
        result=self.build()
        self.assertEqual(int.from_bytes(result[0x14E:0x150],'big'),
                         (sum(result[:0x14E])+sum(result[0x150:]))&65535)


if __name__=='__main__':
    unittest.main()
