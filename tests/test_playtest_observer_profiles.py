"""#61 observer registration must not silently fall back to legacy fixtures."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'),str(ROOT/'scripts/diagnostics')]
import playtest_successor_lineage as lineage
import verify_low_health_flicker as health
import verify_release_candidate as release


class ObserverProfileTests(unittest.TestCase):
    def test_unchanged_component_ranges_are_required(self):
        with patch.object(lineage,'is_candidate',return_value=True),patch.object(lineage,'authenticated_parent',return_value=b'parent') as parent:
            self.assertEqual(health.observer_profile_sha(b'child'),hashlib.sha256(b'parent').hexdigest())
            parent.assert_called_once_with(b'child',(19*0x4000,22*0x4000),(0x42A7,0x436E),(0x09BE,0x09C4))

    def test_modified_component_is_not_accepted(self):
        with patch.object(lineage,'is_candidate',return_value=True),patch.object(lineage,'authenticated_parent',side_effect=ValueError('changed observer')):
            for function in (health.owner_address,health.bulk_compiler_profile,health.publication_route_profile):
                with self.assertRaisesRegex(ValueError,'changed observer'):
                    function(b'child')

    def test_unknown_rom_keeps_its_own_identity(self):
        self.assertEqual(health.observer_profile_sha(b'unknown'),hashlib.sha256(b'unknown').hexdigest())
        self.assertEqual(health.owner_address(b'unknown'),0xFFA5)
        self.assertEqual(health.bulk_compiler_profile(b'unknown'),'')

    def test_successor_requires_its_fresh_hazard_fixture(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='test-observer-') as folder:
            rom=Path(folder)/'candidate.gb'
            rom.write_bytes(bytes(0x100000))
            with patch.object(lineage,'is_candidate',return_value=True),patch.object(health,'observer_profile_sha',return_value=lineage.PARENT_SHA):
                gates={g.name:g for g in release.build_gates(rom,Path(folder)/'out')}
            gate=gates['low_health_flicker']
            self.assertEqual(gate.dependencies,('stage1_current_hazard_state',))
            for flag in ('--boot-derived-state','--hazard-state-receipt','--require-scene0b-low-health','--trace-scanner'):
                self.assertIn(flag,gate.command)
            self.assertNotIn('--require-music-transition',gate.command)


if __name__=='__main__':unittest.main()
