"""Issue #31: synthetic patch boundaries and full-record negative controls.

These tests do not replace emulator combat or destination-copy validation.
"""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_native_projectile_templates as builder
import verify_native_projectile_templates as oracle


class ProjectileTemplateTests(unittest.TestCase):
    def setUp(self):
        self.stock=bytes(range(256))*1024
        parent=bytearray(b'\xff'*0x100000)
        parent[0x147:0x149]=bytes((0x1B,5))
        parent[0x80000:0x84000]=self.stock[0x34000:0x38000]
        parent[0x2AE0:0x2AE0+len(builder.LOADER)]=builder.LOADER
        self.parent=bytes(parent)
        pins=patch.multiple(builder,PARENTS={builder.sha(self.parent)},
                            STOCK_SHA=builder.sha(self.stock))
        pins.start()
        self.addCleanup(pins.stop)

    def test_only_bank_operand_and_checksum_change(self):
        result=builder.build(self.parent,self.stock)
        self.assertEqual(len(result),len(self.parent))
        changed={i for i,(a,b) in enumerate(zip(result,self.parent)) if a!=b}
        self.assertLessEqual(changed,{0x2AE1,0x14E,0x14F})
        self.assertEqual(result[0x2AE1],32)
        self.assertEqual(int.from_bytes(result[0x14E:0x150],'big'),
                         (sum(result[:0x14E])+sum(result[0x150:]))&65535)

    def test_unknown_parent_rejected(self):
        with self.assertRaises(ValueError):
            builder.build(self.parent[:-1]+b'\0',self.stock)

    def test_structural_guards_even_if_parent_is_repinned(self):
        for offset in (0x147,0x148,0x80000,0x2AE0):
            with self.subTest(offset=offset):
                changed=bytearray(self.parent)
                changed[offset]^=1
                with patch.object(builder,'PARENTS',{builder.sha(changed)}):
                    with self.assertRaises(ValueError):
                        builder.build(changed,self.stock)

    def row(self,bank=32,address=0x5CFE):
        offset=bank*0x4000+address-0x4000
        return f'5516 {bank:X} {address:X} {self.parent[offset:offset+48].hex()}'

    def test_all_48_original_bytes_pass(self):
        result=oracle.compare([self.row()],self.stock,self.parent)
        self.assertTrue(result['passed'])
        self.assertEqual(result['observations'],1)

    def test_inactive_tail_corruption_fails(self):
        # Original inactive records are semantically significant, not padding.
        stock=bytearray(self.stock)
        stock[0x35CFE:0x35D2E]=bytes.fromhex('030B0810FA32030B0800FA32')+bytes(36)
        rom=bytearray(self.parent)
        rom[0x81CFE:0x81D2E]=stock[0x35CFE:0x35D2E]
        rom[0x81CFE+47]=0xB7
        row=f'5516 20 5CFE {rom[0x81CFE:0x81D2E].hex()}'
        result=oracle.compare([row],stock,rom)
        self.assertFalse(result['passed'])
        self.assertEqual(result['failures'][0]['differing_offsets'],[47])

    def test_source_binding_is_required(self):
        row=self.row().rsplit(' ',1)[0]+' '+('00'*48)
        with self.assertRaises(ValueError):
            oracle.compare([row],self.stock,self.parent)

    def test_empty_malformed_and_out_of_bounds_rejected(self):
        for rows in ([],['bad'],['0 20 5CFE '+('00'*48)],
                     ['1 -1 5CFE '+('00'*48)],['1 40 5CFE '+('00'*48)],
                     ['1 20 7FD1 '+('00'*48)],['1 20 5CFE 00']):
            with self.subTest(rows=rows):
                with self.assertRaises(ValueError):
                    oracle.compare(rows,self.stock,self.parent)

    def test_truncated_reference_rejected(self):
        with self.assertRaises(ValueError):
            oracle.compare([self.row()],self.stock[:0x34000],self.parent)

    def copy_row(self):
        frame,bank,address,source=self.row().split()
        data=bytearray.fromhex(source)
        for offset in range(0,48,6):
            data[offset+2]=(data[offset+2]+0xFA)&255
            data[offset+3]=(data[offset+3]+0xFE)&255
        return f'{frame} {bank} {address} FEFA DC55 {source} {data.hex()}'

    def test_copy_matches_native_xy_addition_including_wrap(self):
        self.assertTrue(oracle.compare_copies([self.copy_row()],self.stock,self.parent)['passed'])

    def test_copy_damage_byte_mutation_fails(self):
        parts=self.copy_row().split()
        data=bytearray.fromhex(parts[-1])
        data[47]^=1
        parts[-1]=data.hex()
        result=oracle.compare_copies([' '.join(parts)],self.stock,self.parent)
        self.assertFalse(result['passed'])
        self.assertEqual(result['copy_failures'][0]['differing_offsets'],[47])

    def test_copy_truncation_and_wrong_destination_fail(self):
        for row in (self.copy_row()[:-2],self.copy_row().replace('DC55','DC56')):
            with self.assertRaises(ValueError):
                oracle.compare_copies([row],self.stock,self.parent)


if __name__=='__main__':
    unittest.main()
