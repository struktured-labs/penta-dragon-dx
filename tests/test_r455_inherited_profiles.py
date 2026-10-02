"""Exact composition proof and fail-closed inherited observer profiles."""
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'scripts/diagnostics')]
import compose_boss_sync_dma_r454 as dma
import compose_arena_palette_storage_r455 as storage
import compose_attract_blank_r456c as blank
import compose_attract_blank_r456d as scoped
from generate_stream_boss_states import relocated_ted_latches, ENTRY_WHITE_SHA256
from arena_palette_storage import arena_palette_table
from verify_stage1_spike_palettes import publication_boundary, semantic_expansion_is_exact
from verify_low_health_flicker import publication_route_profile, R455_WRONG_DESTINATION_SHA256
from verify_low_health_flicker import owner_address, bulk_compiler_profile
from verify_stage1_exact_destination_mutation import AUTHORITATIVE_DESTINATION, FORCED_WRONG_DESTINATION
from stage_card_palette_handoff import inspect_stage_card_palette_handoff


class InheritedProfiles(unittest.TestCase):
    def test_r456d_exact_inheritance(self):
        rom = scoped.build(self.rom)
        self.assertIn(hashlib.sha256(rom).hexdigest(), ENTRY_WHITE_SHA256)
        self.assertTrue(relocated_ted_latches(rom))
        self.assertTrue(semantic_expansion_is_exact(rom))
        self.assertEqual(publication_route_profile(rom), 'r451c-bounded-room03')
        self.assertEqual(owner_address(rom), 0xFF01)
        self.assertTrue(bulk_compiler_profile(rom))
        self.assertTrue(inspect_stage_card_palette_handoff(rom)['installed'])
        self.assertEqual(publication_boundary(rom)['variant'], 'r456d-attract-white-69896bb1')
        for bank in range(32):
            if bank not in (0,1,18):
                self.assertEqual(rom[bank*16384:(bank+1)*16384], self.rom[bank*16384:(bank+1)*16384])
        for target in range(9):
            self.assertEqual(arena_palette_table(rom,target),arena_palette_table(self.rom,target))
        changed=bytearray(rom)
        changed[0x4EBD4:0x4EBE0]=FORCED_WRONG_DESTINATION
        self.assertEqual(hashlib.sha256(changed).hexdigest(),'ccd31659f45da38df7783be3c0d2c6e48f8fb11cc7ab9b5555971df8088eed91')
        self.assertEqual(publication_route_profile(changed),'r451c-bounded-room03')
        with self.assertRaises(RuntimeError): publication_boundary(changed)
        for offset in (0x14F,0x416C,18*16384+0x2C80,0x12F8,13*16384+0x3457):
            changed=bytearray(rom);changed[offset]^=1
            self.assertFalse(relocated_ted_latches(changed))
            self.assertEqual(publication_route_profile(changed),'')
            self.assertFalse(inspect_stage_card_palette_handoff(changed)['installed'])
            with self.assertRaises(RuntimeError): publication_boundary(changed)

    @classmethod
    def setUpClass(cls):
        path = ROOT / 'tmp/arena-palette-storage-r455/candidate.gb'
        if not path.exists() or not dma.BASE.exists():
            raise unittest.SkipTest('local immutable candidates unavailable')
        cls.rom, cls.base = path.read_bytes(), dma.BASE.read_bytes()

    def test_composition_and_inherited_banks(self):
        self.assertEqual(storage.build(dma.build(self.base))[0], self.rom)
        for bank in (1, 19, 20, 21, 22):
            self.assertEqual(self.base[bank*16384:(bank+1)*16384],
                             self.rom[bank*16384:(bank+1)*16384])
        self.assertEqual(self.base[:0x14D], self.rom[:0x14D])
        self.assertEqual(self.base[0x150:0x4000], self.rom[0x150:0x4000])

    def test_r456c_inherits_only_exact_observer_profiles(self):
        rom = blank.build(self.rom)
        self.assertTrue(semantic_expansion_is_exact(rom))
        self.assertEqual(publication_route_profile(rom), 'r451c-bounded-room03')
        self.assertEqual(owner_address(rom), 0xFF01)
        self.assertTrue(bulk_compiler_profile(rom))
        self.assertTrue(inspect_stage_card_palette_handoff(rom)['installed'])
        for target in range(9):
            self.assertEqual(arena_palette_table(rom,target), arena_palette_table(self.rom,target))
        lua = (ROOT/'scripts/diagnostics/probe_stage1_spike_palettes.lua').read_text()
        self.assertIn('"'+publication_boundary(rom)['variant']+'"',lua)
        changed=bytearray(rom)
        changed[0x4EBD4:0x4EBE0]=FORCED_WRONG_DESTINATION
        self.assertEqual(hashlib.sha256(changed).hexdigest(),
                         'b6d2652e5aed641a2b3bb4f47763ba5fb118ff1d753f6c89f498c95042fd69d9')
        self.assertEqual(publication_route_profile(changed), 'r451c-bounded-room03')
        with self.assertRaises(RuntimeError): publication_boundary(changed)
        for offset in (0x14F,0x416C,18*16384+0x2C80,0x12F8,13*16384+0x3457):
            changed=bytearray(rom);changed[offset]^=1
            self.assertEqual(publication_route_profile(changed),'')
            self.assertEqual(owner_address(changed),0xFFA5)
            self.assertEqual(bulk_compiler_profile(changed),'')
            self.assertFalse(inspect_stage_card_palette_handoff(changed)['installed'])
            with self.assertRaises(RuntimeError): publication_boundary(changed)

    def test_exact_profiles_and_unknown_mutation_rejected(self):
        self.assertEqual(publication_boundary(self.rom)['variant'], 'r455-arena-storage-6e5e7a61')
        self.assertTrue(semantic_expansion_is_exact(self.rom))
        self.assertEqual(publication_route_profile(self.rom), 'r451c-bounded-room03')
        self.assertEqual(owner_address(self.rom), 0xFF01)
        self.assertTrue(bulk_compiler_profile(self.rom))
        lua = (ROOT / 'scripts/diagnostics/probe_stage1_spike_palettes.lua').read_text()
        self.assertIn('"' + publication_boundary(self.rom)['variant'] + '"', lua)
        self.assertEqual(inspect_stage_card_palette_handoff(self.rom)['variant'], 'runtime-receipted-r455')
        for offset in (0x14F, 0x12F8, 13*16384+0x3457, 19*16384+0x2B70):
            changed = bytearray(self.rom)
            changed[offset] ^= 1
            with self.assertRaises(RuntimeError):
                publication_boundary(changed)
            self.assertEqual(publication_route_profile(changed), '')
            self.assertEqual(owner_address(changed), 0xFFA5)
            self.assertEqual(bulk_compiler_profile(changed), '')
            self.assertFalse(inspect_stage_card_palette_handoff(changed)['installed'])

    def test_negative_control_is_exact_and_not_release_admitted(self):
        changed = bytearray(self.rom)
        self.assertEqual(changed[0x4EBD4:0x4EBE0], AUTHORITATIVE_DESTINATION)
        changed[0x4EBD4:0x4EBE0] = FORCED_WRONG_DESTINATION
        self.assertEqual(hashlib.sha256(changed).hexdigest(), R455_WRONG_DESTINATION_SHA256)
        self.assertEqual(publication_route_profile(changed), 'r451c-bounded-room03')
        with self.assertRaises(RuntimeError):
            publication_boundary(changed)
        changed[0x4EBE0] ^= 1
        self.assertEqual(publication_route_profile(changed), '')


if __name__ == '__main__':
    unittest.main()
