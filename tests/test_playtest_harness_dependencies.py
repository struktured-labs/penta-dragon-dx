"""#61: closed successor controls and fresh Crystal isolation dependency."""
from pathlib import Path
import sys
import unittest
import zlib
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
import hazard_mutations_r442 as hazard
import playtest_successor_lineage as lineage
from verify_release_candidate import build_gates
from verify_crystal_dragon_ghost import verify_exact_stage3_payload


class HarnessDependenciesTest(unittest.TestCase):
    def source(self):
        rom = bytearray(0x100000)
        for address, value in ((0x1B72, 'AFE0E4C9'), (0x1DCB, 'AFE0E4C9'),
                               (0x4E2D4, '0B'), (0x4E2CB, '9E6D'), (0x4E1A5, '0A')):
            data = bytes.fromhex(value)
            rom[address:address + len(data)] = data
        return bytes(rom)

    def test_successor_control_remains_closed_and_component_bound(self):
        source = self.source()
        plans = {
            'forced-visible-menu-repair': ((0x1B72, 'CDA042C9'), (0x1DCB, 'CDA042C9')),
            'short-endpoint-span': ((0x4E2D4, '0A'),),
            'missing-alternate-phase': ((0x4E2CB, 'F661'),),
            'short-right-endpoint-span': ((0x4E1A5, '09'),),
        }
        with patch.object(lineage, 'is_candidate', return_value=True), patch.object(
            lineage, 'authenticated_parent', return_value=b'not executed'
        ) as authenticate:
            for name, patches in plans.items():
                result = bytearray(source)
                for address, value in patches:
                    data = bytes.fromhex(value)
                    result[address:address + len(data)] = data
                result[0x14E:0x150] = ((sum(result[:0x14E]) + sum(result[0x150:])) & 65535).to_bytes(2, 'big')
                self.assertEqual(hazard.authenticate(source, bytes(result)), name)
                result[0x200] ^= 1
                with self.assertRaisesRegex(ValueError, 'exact approved'):
                    hazard.authenticate(source, bytes(result))
            authenticate.assert_called_with(source, (0x1B6F, 0x1B76),
                                             (0x1DC8, 0x1DCF), (0x4C000, 0x50000))
            with self.assertRaisesRegex(ValueError, 'exact approved'):
                hazard.authenticate(source, source)

    def test_failed_component_authentication_cannot_use_plans(self):
        with patch.object(lineage, 'is_candidate', return_value=True), patch.object(
            lineage, 'authenticated_parent', side_effect=ValueError('changed component')
        ):
            with self.assertRaisesRegex(ValueError, 'changed component'):
                hazard.authenticate(self.source(), b'anything')

    def test_crystal_gets_current_generated_stage3_and_dependency(self):
        output = Path('unit-artifacts')
        gates = {g.name: g for g in build_gates(Path('nonexistent-unit-rom'), output)}
        producer = gates['current_stage_control_states']
        crystal = gates['crystal_dragon_ghost']
        self.assertIn('--force', producer.command)
        self.assertIn('current_stage_control_states', crystal.dependencies)
        self.assertIn('--stage3-exact-rom', crystal.command)
        position = crystal.command.index('--stage3-state')
        self.assertEqual(crystal.command[position + 1],
                         str(output / 'artifacts/current-stage-control-states/stage3.ss0'))

    def test_stage3_exact_identity_and_scene_are_required(self):
        rom = bytearray(0x100000)
        rom[0x143] = 0xC0
        raw = bytearray(0x11800)
        raw[:4] = (0x00400003).to_bytes(4, 'little')
        raw[4:8] = (zlib.crc32(rom) & 0xFFFFFFFF).to_bytes(4, 'little')
        raw[8] = 0x80
        raw[16:32] = rom[0x134:0x144]
        raw[0x5C80], raw[0x3BA] = 4, 2
        verify_exact_stage3_payload(raw, rom)
        for offset in (0, 4, 8, 31, 0x5C80, 0x3BA):
            changed = bytearray(raw)
            changed[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                verify_exact_stage3_payload(changed, rom)


if __name__ == '__main__':
    unittest.main()
