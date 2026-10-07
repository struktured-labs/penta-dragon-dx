"""#61: successor observer inheritance is component-scoped and fail-closed."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'scripts/diagnostics')]
import playtest_successor_lineage as lineage
import generate_stream_boss_states as fixtures
import verify_boss_atomic_attr_contract as atomic
import arena_palette_storage as storage
import expansion_bank_ownership_r456 as ownership
import verify_ted_expanded_integration as ted


class BossObserverTests(unittest.TestCase):
    def test_ted_latch_inheritance_requires_whole_unchanged_bank(self):
        with patch.object(lineage, 'is_candidate', side_effect=[True, False]), \
             patch.object(lineage, 'authenticated_parent', return_value=b'unknown') as parent:
            self.assertFalse(fixtures.relocated_ted_latches(b'child'))
            parent.assert_called_once_with(b'child', (17 * 0x4000, 18 * 0x4000))

    def test_overlay_authenticates_only_exact_fragment_and_owner_set(self):
        owners = {'arena-completion-safe'}
        with patch.object(lineage, 'is_candidate', return_value=True), \
             patch.object(lineage, 'authenticated_parent', return_value=b'parent') as parent, \
             patch.object(atomic.release_lock_lineage, 'overlay', return_value=b'new') as overlay:
            self.assertEqual(atomic.component_overlay(b'child', 0x35600, b'old', owners), b'new')
            parent.assert_called_once_with(b'child', (0x35600, 0x35603))
            overlay.assert_called_once_with(b'parent', 0x35600, b'old', owners)

    def test_table_inheritance_authenticates_both_regions_and_selector(self):
        with patch.object(lineage, 'is_candidate', side_effect=[True, False]), \
             patch.object(lineage, 'authenticated_parent', return_value=bytes(0x100000)) as parent:
            self.assertEqual(storage.arena_palette_table(b'child', 1), bytes(256))
            parent.assert_called_once_with(
                b'child', (23 * 0x4000, 24 * 0x4000),
                (13 * 0x4000 + 0x3200, 13 * 0x4000 + 0x3B00),
                (13 * 0x4000 + 0x2FD5, 13 * 0x4000 + 0x2FE0))

    def test_expansion_inheritance_requires_all_eleven_unchanged_banks(self):
        with patch.object(lineage, 'is_candidate', return_value=True), \
             patch.object(lineage, 'authenticated_parent', return_value=b'parent') as parent, \
             patch.object(ownership, 'inspect_release_lock_tail', return_value={'exact': False}) as inspect:
            self.assertEqual(ownership.inspect_tail(b'child'), {'exact': False})
            parent.assert_called_once_with(b'child', (21 * 0x4000, 32 * 0x4000))
            inspect.assert_called_once_with(b'parent')

    def test_header_inheritance_requires_actual_mapper_and_size_bytes(self):
        with patch.object(lineage, 'is_candidate', return_value=True), \
             patch.object(lineage, 'authenticated_parent', return_value=b'parent') as parent, \
             patch.object(ted.release_lock_lineage, 'is_candidate', return_value=False):
            self.assertFalse(ted.expanded_release_header(b'child'))
            parent.assert_called_once_with(b'child', (0x147, 0x149))

    def test_authentication_failures_are_not_swallowed(self):
        with patch.object(lineage, 'is_candidate', return_value=True), \
             patch.object(lineage, 'authenticated_parent', side_effect=ValueError('changed component')):
            for function in (fixtures.relocated_ted_latches, ownership.inspect_tail,
                             ted.expanded_release_header,
                             lambda rom: storage.arena_palette_table(rom, 1),
                             lambda rom: atomic.component_overlay(rom, 0x35600, b'abc', set())):
                with self.assertRaisesRegex(ValueError, 'changed component'):
                    function(b'child')


if __name__ == '__main__':
    unittest.main()
