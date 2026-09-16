from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
import verify_stage1_scene0b_live_menu_roundtrip as live


class SourceResumeTests(unittest.TestCase):
    def test_exact_archived_wall_state_rejects_relocated_return(self):
        state = live.gbas_payload(ROOT/'save_states_for_claude/rc11_corrupted-walls.ss0')
        rom = bytearray((ROOT/'rom/Penta Dragon (J).gb').read_bytes())
        live.check_known_source_resume(state, rom)
        rom[0x13C0:0x13C5] = bytes.fromhex('F5 F0 BA B7 20')
        with self.assertRaisesRegex(live.LiveError, 'saved IRQ return'):
            live.check_known_source_resume(state, rom)

    def test_other_capture_is_not_rejected_by_specific_stack_check(self):
        state = live.gbas_payload(ROOT/'save_states_for_claude/rc11_low-health-degradation.ss0')
        rom = bytearray(0x1400)
        rom[0x13C0:0x13C5] = bytes.fromhex('F5 F0 BA B7 20')
        live.check_known_source_resume(state, rom)


if __name__ == '__main__':
    unittest.main()
