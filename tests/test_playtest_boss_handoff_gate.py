import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
import verify_playtest_boss_handoff as gate
import verify_live_regression as live


class BossHandoffGateTest(unittest.TestCase):
    def test_unknown_candidate_rejected(self):
        with self.assertRaisesRegex(ValueError, 'exact'):
            gate.broken_control(bytes(0x100000))

    def test_control_only_restores_prelude_and_checksum(self):
        rom = bytearray(0x100000)
        start = gate.layout.HOOK
        rom[start:start + len(gate.layout.NEW)] = gate.layout.NEW
        expected = bytearray(rom)
        expected[start:start + len(gate.layout.OLD)] = gate.layout.OLD
        expected[0x14E:0x150] = (sum(expected) & 65535).to_bytes(2, 'big')
        with patch.object(gate.lineage, 'is_candidate', return_value=True), patch.object(
            gate.layout, 'PARENT', hashlib.sha256(expected).hexdigest()
        ):
            self.assertEqual(gate.broken_control(bytes(rom)), expected)

    def test_recognized_but_wrong_prelude_rejected(self):
        with patch.object(gate.lineage, 'is_candidate', return_value=True):
            with self.assertRaisesRegex(ValueError, 'preimage'):
                gate.broken_control(bytes(0x100000))

    def test_pre_stream_profile_requires_handoff_gate(self):
        name = 'playtest_secret_boss_handoff'
        with patch.object(live, 'registered_gate_names', return_value={name}):
            selected, errors = live.profile_gates(Path('unit-only'))
        self.assertEqual(selected, (name,))
        self.assertEqual(errors, [])


if __name__ == '__main__':
    unittest.main()
