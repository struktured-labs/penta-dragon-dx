from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))
import build_title_tile_retire_trial_r535 as trial


class TitleTileRetireTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "tmp/stage4-cache-key-r534/candidate.gb").read_bytes()

    def test_only_title_operand_changes_beyond_independent_menu_fix(self):
        menu = trial.menu.build(self.source, True, True)
        result = trial.build(self.source)
        delta = {i for i, (a, b) in enumerate(zip(menu, result, strict=True)) if a != b}
        self.assertEqual(delta - {0x14E, 0x14F}, {trial.VBK_IMMEDIATE})
        self.assertEqual(result[trial.VBK_IMMEDIATE-1:trial.VBK_IMMEDIATE+3],
                         bytes.fromhex("3E 00 E0 4F"))

    def test_original_branch_loop_lcd_marker_and_continuation_are_unchanged(self):
        result = trial.build(self.source)
        front = bytearray(result[trial.FRONT:trial.FRONT+len(trial.OLD_FRONT)])
        front[14] = 1
        self.assertEqual(bytes(front), trial.OLD_FRONT)
        self.assertEqual(result[0x3B42:0x3B56], self.source[0x3B42:0x3B56])
        wrapper = 13 * 0x4000 + 0x36D7
        self.assertEqual(result[wrapper:wrapper+14], self.source[wrapper:wrapper+14])
        checksum = (sum(result[:0x14E]) + sum(result[0x150:])) & 0xFFFF
        self.assertEqual(result[0x14E:0x150], checksum.to_bytes(2, "big"))

    def test_unknown_source_is_rejected(self):
        changed = bytearray(self.source)
        changed[trial.VBK_IMMEDIATE] = 0
        with self.assertRaises(ValueError):
            trial.build(changed)

    def test_inherited_component_recognition_is_bound_to_exact_rom(self):
        from stage_card_palette_handoff import inspect_stage_card_palette_handoff
        from verify_stage1_spike_palettes import publication_boundary, semantic_expansion_is_exact
        result = trial.build(self.source)
        self.assertTrue(inspect_stage_card_palette_handoff(result)["installed"])
        self.assertEqual(publication_boundary(result)["pc"], 0x7457)
        self.assertTrue(semantic_expansion_is_exact(result))
        for offset in (0x14F, trial.VBK_IMMEDIATE, 0x37000):
            changed = bytearray(result)
            changed[offset] ^= 1
            self.assertFalse(inspect_stage_card_palette_handoff(changed)["installed"])
            with self.assertRaises(RuntimeError):
                publication_boundary(changed)

    def test_inherited_tables_and_observer_abis_are_exact(self):
        from arena_palette_storage import arena_palette_table
        from generate_stream_boss_states import relocated_ted_latches
        from verify_low_health_flicker import publication_route_profile, owner_address, bulk_compiler_profile
        from verify_menu_icon_palettes import menu_oracle, BANK20_LUT, MENU_RESERVED_HAZARDS
        from verify_stage1_no_bleed import expected_stage1_table
        from verify_stage1_pickup_art import expected_stage1_table as pickup_table
        result = trial.build(self.source)
        self.assertEqual(publication_route_profile(result), "r451c-bounded-room03")
        self.assertEqual(owner_address(result), 0xFF01)
        self.assertTrue(bulk_compiler_profile(result))
        self.assertTrue(relocated_ted_latches(result))
        expected, forbidden = menu_oracle(result)
        self.assertEqual(expected, result[BANK20_LUT:BANK20_LUT+256])
        self.assertEqual(forbidden, frozenset(MENU_RESERVED_HAZARDS))
        self.assertEqual(expected_stage1_table(result), expected_stage1_table(self.source))
        self.assertEqual(pickup_table(result), pickup_table(self.source))
        for target in range(9):
            self.assertEqual(arena_palette_table(result, target), arena_palette_table(self.source, target))
        changed = bytearray(result)
        changed[0x14F] ^= 1
        self.assertEqual(publication_route_profile(changed), "")
        self.assertEqual(owner_address(changed), 0xFFA5)
        self.assertFalse(bulk_compiler_profile(changed))
        self.assertFalse(relocated_ted_latches(changed))
        self.assertFalse(menu_oracle(changed)[1])

    def test_current_boot_derived_hazard_route_is_selected(self):
        from verify_release_candidate import build_gates
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as scratch:
            path = Path(scratch) / "candidate.gb"
            path.write_bytes(trial.build(self.source))
            gates = {g.name:g for g in build_gates(path, Path(scratch) / "matrix")}
            gate = gates["low_health_flicker"]
            self.assertEqual(gate.dependencies, ("stage1_current_hazard_state",))
            self.assertIn("--boot-derived-state", gate.command)
            self.assertIn("--require-scene0b-low-health", gate.command)

    def test_lua_publisher_initialization_accepts_only_bound_name_and_bytes(self):
        lua = shutil.which("lua")
        if lua is None:
            self.skipTest("standalone Lua interpreter unavailable")
        source = (ROOT / "scripts/diagnostics/probe_stage1_spike_palettes.lua").read_text()
        start = source.index("PENTA_PRIMARY_ADDR =")
        end = source.index('if watchdog then watchdog:write("init:publication-match')
        prefix = source[start:end]
        rom = trial.build(self.source)
        body = rom[0x12E0:0x1303]
        cases = (("r535-title-tile-retire-681b4668", body, True),
                 ("unknown-rom", body, False),
                 ("r535-title-tile-retire-681b4668", bytes([body[0]^1])+body[1:], False))
        for name, payload, accepted in cases:
            # Only the actual initialization prefix runs, against a read-only
            # ROM-byte stub. This is standalone Lua, never an emulator launch.
            setup = (
                f"PENTA_EXPECTED_PUBLICATION_VARIANT={json.dumps(name)}\n"
                f"local payload=string.char({','.join(map(str,payload))})\n"
                "emu={read8=function(self,address) return assert(payload:byte(address-0x12E0+1)) end}\n"
            )
            run = subprocess.run([lua, "-"], input=setup+prefix, text=True,
                                 capture_output=True, timeout=5)
            self.assertEqual(run.returncode == 0, accepted, run.stderr)
            if not accepted:
                self.assertIn("requires exactly one reviewed publisher", run.stderr)

    def test_hazard_negative_controls_remain_exact(self):
        from hazard_mutations_r442 import authenticate
        result = trial.build(self.source)
        changed = bytearray(result)
        for offset in (0x1B72, 0x1DCB):
            self.assertEqual(changed[offset:offset+4], bytes.fromhex("AF E0 E4 C9"))
            changed[offset:offset+4] = bytes.fromhex("CD A0 42 C9")
        changed[0x14E:0x150] = ((sum(changed[:0x14E])+sum(changed[0x150:]))&65535).to_bytes(2,"big")
        self.assertEqual(authenticate(result, changed), "forced-visible-menu-repair")
        changed[0x100] ^= 1
        with self.assertRaises(ValueError):
            authenticate(result, changed)
