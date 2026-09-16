from pathlib import Path
import json
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
sys.path.insert(0,str(ROOT/'tests'))
import verify_natural_stage1_obj as oracle
from test_stage1_obj_visual_contract import PRIMARY_HEX, VARIANT_HEX


class NaturalObjTests(unittest.TestCase):
    def setUp(self):
        rom = bytearray(oracle.obj.ROM_SIZE)
        stock = (ROOT/'rom/Penta Dragon (J).gb').read_bytes()
        rom[:len(stock)] = stock
        start = oracle.obj.OBJ_PRIMARY_OFFSET
        rom[start:start+len(bytes.fromhex(PRIMARY_HEX))] = bytes.fromhex(PRIMARY_HEX)
        start = oracle.obj.OBJ_VARIANT_OFFSET
        rom[start:start+len(bytes.fromhex(VARIANT_HEX))] = bytes.fromhex(VARIANT_HEX)
        self.rom = bytes(rom)
        self.atlas = oracle.graphics_authority(self.rom)
        self.contract = oracle.obj.candidate_contract(self.rom)
        self.data = bytearray(4326)
        self.data[:0x800] = self.atlas
        self.data[4096:4160] = oracle.obj.expected_obj_cram(self.contract,ffbf=0,ffc0=0,ffd0=0)
        self.data[4160:4168] = bytes([88,80,0x20,2,88,88,0x21,2])
        self.data[-6:] = bytes([0x8B,0,0,0,0,0xF9])

    def check(self,data):
        return oracle.check_snapshot(data,self.atlas,self.contract)

    def test_sara_and_unseen_but_rom_owned_enemy_animation_pass(self):
        self.assertEqual(self.check(self.data)['sara_entries'],2)
        for tile in (0x50,0x54):
            self.data[4176:4184] = bytes([9,93,tile+1,0x24,9,101,tile,0x24])
            self.assertEqual(self.check(self.data)['visible_entries'],4)

    def test_floor_bleed_priority_is_rejected(self):
        self.data[4163] |= 0x80
        with self.assertRaisesRegex(ValueError,'floor'):
            self.check(self.data)

    def test_chr_corruption_fails_even_if_it_predates_menu(self):
        self.data[0x200] ^= 1
        with self.assertRaisesRegex(ValueError,'original-ROM atlas'):
            self.check(self.data)

    def test_palette_and_wrong_vram_bank_fail(self):
        changed = bytearray(self.data)
        changed[4100] ^= 1
        with self.assertRaisesRegex(ValueError,'CRAM'):
            self.check(changed)
        changed = bytearray(self.data)
        changed[4163] |= 8
        with self.assertRaisesRegex(ValueError,'unauthenticated CHR'):
            self.check(changed)

    def test_changed_rom_cannot_define_its_own_sprite_oracle(self):
        changed = bytearray(self.rom)
        changed[0x21000] ^= 1
        with self.assertRaisesRegex(ValueError,'ROM source changed'):
            oracle.graphics_authority(changed)

    def test_source_page_evidence_is_json_roundtrip_stable(self):
        evidence = oracle.source_page_evidence()
        self.assertEqual(evidence, json.loads(json.dumps(evidence)))
        self.assertTrue(all(isinstance(row, list) for row in evidence))
        self.assertEqual(
            evidence,
            [[address, digest] for address, digest in oracle.SOURCES],
        )

    def test_wrapped_enemy_quad_authenticates_visible_halves(self):
        self.data[4160 + 8 * 4:4160 + 12 * 4] = bytes([
            81, 255, 0x69, 0x25, 81, 7, 0x68, 0x25,
            89, 255, 0x6B, 0x25, 89, 7, 0x6A, 0x25,
        ])
        native = oracle.native_stage1_enemy_quads(self.rom)
        owned = oracle.native_enemy_oam(self.data, native)
        self.assertEqual(set(owned), {8, 9, 10, 11})
        self.assertEqual(owned[9], ('68', '25'))


if __name__ == '__main__':
    unittest.main()
