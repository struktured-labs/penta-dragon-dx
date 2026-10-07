"""#59: changed runtime ownership must not bypass unrelated components."""
from pathlib import Path
import hashlib
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'scripts/diagnostics')]
import lowhealth_candidate_lineage as lowhealth
import playtest_successor_lineage as successor
import release_lock_lineage as release
import verify_stage1_captured_menu as menu
import stage_card_palette_handoff as card


class LowhealthComponentContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = (ROOT / 'tmp/later-lowhealth-camera-source-01/candidate.gb').read_bytes()
        if not lowhealth.is_candidate(cls.rom):
            raise RuntimeError('exact source candidate required')

    def test_changed_dispatcher_is_not_unchanged_inheritance(self):
        with self.assertRaisesRegex(ValueError, 'intersects'):
            lowhealth.authenticated_parent(self.rom, (0x3569a, 0x356ff))
        parent = lowhealth.dispatcher_component_parent(self.rom, (0x3569a, 0x356ff))
        self.assertEqual(hashlib.sha256(parent).hexdigest(), lowhealth.PARENT_SHA)

    def test_other_changes_are_not_dispatcher_owned(self):
        for offset, _, _ in lowhealth.RUNS:
            if offset in {0x356ea, 0x356ec, 0x356fc, 0x356fe}:
                continue
            with self.subTest(offset=hex(offset)):
                with self.assertRaisesRegex(ValueError, 'unowned'):
                    lowhealth.dispatcher_component_parent(self.rom, (offset, offset + 1))

    def test_bad_ranges_and_unknown_image_fail(self):
        for ranges in ((), ((0, 0),), ((-1, 1),), ((0, len(self.rom) + 1),)):
            with self.assertRaises(ValueError):
                lowhealth.dispatcher_component_parent(self.rom, *ranges)
        changed = bytearray(self.rom)
        changed[0x356d0] ^= 1
        with self.assertRaisesRegex(ValueError, 'exact'):
            lowhealth.dispatcher_component_parent(changed, (0x3569a, 0x356ff))

    def test_menu_component_contract_and_candidate_runtime_refresh(self):
        contract = menu.menu_contract_rom(self.rom)
        self.assertEqual(hashlib.sha256(contract).hexdigest(), successor.PARENT_SHA)
        ancestor = release.ancestor_bytes(contract, 0, 32 * 0x4000,
                                          set().union(*release.RUN_OWNERS.values()))
        raw = bytearray(71680)
        allowed = set()
        for address, source, length in menu.RELEASE_LOCK_WRAM_IMAGES:
            start = 0x5400 + address - 0xd000
            raw[start:start+length] = ancestor[source:source+length]
            allowed.update(range(start, start + length))
        before = bytes(raw)
        records = menu.release_lock_runtime_refresh(raw, self.rom)
        self.assertEqual(len(records), len(menu.RELEASE_LOCK_WRAM_IMAGES))
        for address, source, length in menu.RELEASE_LOCK_WRAM_IMAGES:
            start = 0x5400 + address - 0xd000
            self.assertEqual(raw[start:start+length], self.rom[source:source+length])
        self.assertTrue({i for i, (a, b) in enumerate(zip(before, raw)) if a != b} <= allowed)
        wrong = bytearray(before)
        wrong[0x5fc8] ^= 1
        with self.assertRaisesRegex(ValueError, 'installer image'):
            menu.release_lock_runtime_refresh(wrong, self.rom)

    def test_card_contract_accepts_exact_child_and_rejects_bridge_damage(self):
        result = card.inspect_stage_card_palette_handoff(self.rom)
        self.assertTrue(result['installed'])
        self.assertTrue(result['variant'].startswith('lowhealth-dispatcher-'))
        damaged = bytearray(self.rom)
        damaged[0x356de] ^= 1
        try:
            result = card.inspect_stage_card_palette_handoff(damaged)
        except ValueError:
            return
        self.assertFalse(result['installed'])

    def boundary(self, pc, bank=13, return_word=None):
        raw = bytearray(71680)
        raw[menu.CPU_PC:menu.CPU_PC+2] = pc.to_bytes(2, 'little')
        raw[menu.MEMORY_CURRENT_BANK:menu.MEMORY_CURRENT_BANK+2] = bank.to_bytes(2, 'little')
        sp = 0xdffe if return_word is None else 0xdffc
        raw[menu.CPU_SP:menu.CPU_SP+2] = sp.to_bytes(2, 'little')
        if return_word is not None:
            raw[0x63fc:0x63fe] = return_word.to_bytes(2, 'little')
        return menu.release_lock_boundary(raw, self.rom)

    def test_rom_and_copied_wram_changed_execution_are_unsafe(self):
        for pc in (0x570e, 0xdbe8, 0xdbee):
            with self.subTest(pc=hex(pc)):
                self.assertFalse(self.boundary(pc)['safe'])
        self.assertFalse(self.boundary(0x100, return_word=0x5711)['safe'])
        self.assertFalse(self.boundary(0x100, return_word=0xdbea)['safe'])
        self.assertTrue(self.boundary(0x100)['safe'])

    def test_stage1_bulk_observer_requires_complete_new_source_identity(self):
        import verify_low_health_flicker as flicker
        self.assertEqual(flicker.bulk_compiler_profile(self.rom), 'r426-bulk-v1')
        for offset in (0x7ad04, 0x7b8a0, 0x4324):
            changed = bytearray(self.rom)
            changed[offset] ^= 1
            self.assertEqual(flicker.bulk_compiler_profile(changed), '')

    def test_menu_prelude_cave_requires_source_built_resolver(self):
        import verify_ted_expanded_integration as ted
        base = ted.menu_icons._menu_owned_prelude(ted.build.build_colorize_prelude())
        self.assertTrue(ted.lowhealth_menu_prelude_exact(self.rom, base))
        changed = bytearray(self.rom)
        changed[0x36ee8] ^= 1
        self.assertFalse(ted.lowhealth_menu_prelude_exact(changed, base))


if __name__ == '__main__':
    unittest.main()
