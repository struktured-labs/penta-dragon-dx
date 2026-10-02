"""Prevent banked compiler samples from resetting the native menu anchor."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MenuAnchorBanks(unittest.TestCase):
    def test_d82_does_not_bypass_room_stabilization(self):
        verifier = (ROOT / 'scripts/diagnostics/verify_stage1_current_hazard_menu.py').read_text()
        self.assertIn('menu_anchor_room = 0x01', verifier)
        self.assertNotIn('menu_anchor_room = -1', verifier)

    def test_every_frame_capture_timeout_fits_outer_gate(self):
        verifier = (
            ROOT / 'scripts/diagnostics/verify_stage1_current_hazard_menu.py'
        ).read_text()
        reporter = (
            ROOT
            / 'scripts/diagnostics/verify_stage1_reported_regressions_ready.py'
        ).read_text()
        self.assertIn('DEFAULT_REPLAY_TIMEOUT = 90.0', verifier)
        self.assertIn(
            '"--hazard-menu-timeout", type=float, default=180.0', reporter
        )

    def test_anchor_uses_readability_and_never_raw_banked_scene(self):
        probe = (ROOT / 'scripts/diagnostics/probe_stage1_spike_palettes.lua').read_text()
        anchor = probe.split('local anchor_scene, anchor_unreadable = sampled_scene()', 1)[1]
        anchor = anchor.split('local menu_timeline_ready', 1)[0]
        self.assertNotIn('emu:read8(0xD880)', anchor)
        self.assertIn('and not anchor_unreadable then', anchor)
        self.assertIn('PENTA_MENU_STABLE_FRAMES >= menu_anchor_delay', anchor)
        self.assertIn('PENTA_MENU_STABLE_ROOM == menu_anchor_room', anchor)
        scene = probe.split('local function sampled_scene()', 1)[1].split('local function is_floor_tile', 1)[0]
        self.assertIn('PENTA_R435_PUBLICATION and emu:read8(0xFF99) == 30', scene)
        self.assertIn('pc >= 0x6D00 and pc < 0x7890', scene)
        self.assertIn('emu:read8(0xFF99) == 1', scene)

    def test_native_menu_tail_breakpoint_is_bank_qualified(self):
        probe = (ROOT / 'scripts/diagnostics/probe_stage1_spike_palettes.lua').read_text()
        self.assertIn('end, 0x77A8, 1)', probe)
        self.assertNotIn('end, 0x77A8, -1)', probe)
        rom = (ROOT / 'tmp/stage5-dead-pointer-moves-r435/candidate.gb').read_bytes()
        self.assertEqual(rom[0x77A8:0x77AC], bytes.fromhex('CD 13 00 C9'))
