from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))
import build_stage_card_blank_trial_r535 as trial
import build_title_tile_retire_trial_r535 as title


class StageCardBlankTrialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = title.build((ROOT / "tmp/stage4-cache-key-r534/candidate.gb").read_bytes())

    def test_exact_source_and_deterministic_reconstruction(self):
        self.assertEqual(hashlib.sha256(self.source).hexdigest(), trial.BASE_SHA)
        first = trial.build(self.source)
        self.assertEqual(first, trial.build(self.source))
        checksum = (sum(first[:0x14E]) + sum(first[0x150:])) & 0xFFFF
        self.assertEqual(first[0x14E:0x150], checksum.to_bytes(2, "big"))

    def test_only_gated_loader_fallback_and_owned_slack_change(self):
        result = trial.build(self.source)
        mux, helper = trial.payloads()
        owned = {0x14E, 0x14F}
        for offset, count in ((trial.CALLER, 3),
                              (trial.HOOK, trial.HOOK_END - trial.HOOK),
                              (trial.FALLBACK, 3),
                              (trial.MUX, len(mux)), (trial.HELPER, len(helper))):
            owned.update(range(offset, offset + count))
        delta = {i for i, (x, y) in enumerate(zip(self.source, result, strict=True)) if x != y}
        self.assertLessEqual(delta, owned)
        self.assertEqual(result[trial.CALLER:trial.CALLER+3], bytes.fromhex("CD 79 41"))
        self.assertEqual(result[trial.HOOK:trial.HOOK+5], bytes.fromhex("3E 1F CD 47 08"))
        self.assertEqual(result[trial.HOOK+5:trial.HOOK_END],
                         self.source[trial.HOOK+5:trial.HOOK_END])
        self.assertEqual(result[0x4176:0x417D], bytes.fromhex("C3 E8 01 0E 80 06 13"))
        # Native four-step fade and 100-tick card wait remain unchanged.
        for start, end in ((0x0F33, 0x0F66), (0x10D5, 0x10E2),
                           (0x75C7, 0x75F3), (13*0x4000+0x33FC, 13*0x4000+0x3470)):
            self.assertEqual(result[start:end], self.source[start:end])

    def test_guard_uses_selected_stage_before_gameplay_mode_exists(self):
        mux, helper = trial.payloads()
        self.assertIn(bytes.fromhex("F8 04 7E FE 4B"), mux)
        self.assertIn(bytes.fromhex("23 7E FE 41"), mux)
        self.assertTrue(helper.startswith(bytes.fromhex("FA 80 D8 FE 18")))
        self.assertIn(bytes.fromhex("F0 BA B7"), helper)
        self.assertNotIn(bytes.fromhex("F0 B7"), helper)
        self.assertTrue(helper.endswith(bytes.fromhex("21 85 DC 06 28 3E 01 C9")))

    def test_blank_write_is_atomic_and_restores_bcps(self):
        _, helper = trial.payloads()
        self.assertIn(bytes.fromhex("F0 68 F5 F3 F0 40 CB 7F"), helper)
        self.assertEqual(helper.count(bytes.fromhex("F0 44 FE 90")), 2)
        writes = bytes.fromhex("3E 80 E0 68 AF") + bytes.fromhex("E0 69") * 8
        self.assertIn(writes, helper)
        self.assertIn(bytes.fromhex("F1 E0 68 FB D1"), helper)

    def test_unknown_rom_and_mutated_source_fail_closed(self):
        for offset in (trial.CALLER, trial.HOOK, trial.HOOK_END - 1,
                       trial.FALLBACK, trial.MUX, trial.HELPER, 0x14F):
            source = bytearray(self.source)
            source[offset] ^= 1
            with self.assertRaises(ValueError):
                trial.build(source)

    def test_handoff_profile_is_exact_and_keeps_byte_checks(self):
        from stage_card_palette_handoff import inspect_stage_card_palette_handoff
        result = trial.build(self.source)
        self.assertTrue(inspect_stage_card_palette_handoff(result)["installed"])
        for offset in (0x14F, 13*0x4000+0x3459, trial.HOOK):
            changed = bytearray(result)
            changed[offset] ^= 1
            self.assertFalse(inspect_stage_card_palette_handoff(changed)["installed"])

    def test_publisher_and_semantic_oracles_keep_exact_identity(self):
        from verify_stage1_spike_palettes import publication_boundary, semantic_expansion_is_exact
        result = trial.build(self.source)
        self.assertEqual(publication_boundary(result)["pc"], 0x7457)
        self.assertTrue(semantic_expansion_is_exact(result))
        for offset in (0x14F, 0x12E0, 0x37000):
            changed = bytearray(result)
            changed[offset] ^= 1
            with self.assertRaises(RuntimeError):
                publication_boundary(changed)

    def test_inherited_data_and_observer_profiles_are_unchanged(self):
        from arena_palette_storage import arena_palette_table
        from generate_stream_boss_states import relocated_ted_latches
        from verify_low_health_flicker import publication_route_profile, owner_address, bulk_compiler_profile
        from verify_menu_icon_palettes import menu_oracle
        from verify_stage1_no_bleed import expected_stage1_table
        from verify_stage1_pickup_art import expected_stage1_table as pickup_table
        result = trial.build(self.source)
        for probe in (publication_route_profile, owner_address, bulk_compiler_profile,
                      relocated_ted_latches, menu_oracle, expected_stage1_table, pickup_table):
            with self.subTest(probe=probe.__module__ + "." + probe.__name__):
                self.assertEqual(probe(result), probe(self.source))
        for target in range(9):
            self.assertEqual(arena_palette_table(result, target), arena_palette_table(self.source, target))
        changed = bytearray(result)
        changed[0x14F] ^= 1
        self.assertEqual(publication_route_profile(changed), "")
        self.assertFalse(bulk_compiler_profile(changed))
        self.assertFalse(relocated_ted_latches(changed))
        self.assertFalse(menu_oracle(changed)[1])

    def test_current_hazard_fixture_is_required_by_full_matrix(self):
        from verify_release_candidate import build_gates
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as scratch:
            path = Path(scratch) / "candidate.gb"
            path.write_bytes(trial.build(self.source))
            gates = {g.name:g for g in build_gates(path, Path(scratch) / "matrix")}
            gate = gates["low_health_flicker"]
            self.assertEqual(gate.dependencies, ("stage1_current_hazard_state",))
            self.assertIn("--boot-derived-state", gate.command)
            self.assertIn("--require-scene0b-low-health", gate.command)

    def test_actual_lua_publisher_prefix_keeps_name_and_opcode_guards(self):
        lua = shutil.which("lua")
        if lua is None:
            self.skipTest("standalone Lua interpreter unavailable")
        source = (ROOT / "scripts/diagnostics/probe_stage1_spike_palettes.lua").read_text()
        prefix = source[source.index("PENTA_PRIMARY_ADDR ="):
                        source.index('if watchdog then watchdog:write("init:publication-match')]
        body = trial.build(self.source)[0x12E0:0x1303]
        for name, payload, accepted in (
                ("r535-stage-card-black-fe14b0e3", body, True),
                ("unknown-rom", body, False),
                ("r535-stage-card-black-fe14b0e3", bytes([body[0]^1])+body[1:], False)):
            setup = (f"PENTA_EXPECTED_PUBLICATION_VARIANT={json.dumps(name)}\n"
                     f"local payload=string.char({','.join(map(str,payload))})\n"
                     "emu={read8=function(self,address) return assert(payload:byte(address-0x12E0+1)) end}\n")
            run = subprocess.run([lua, "-"], input=setup+prefix, text=True,
                                 capture_output=True, timeout=5)
            self.assertEqual(run.returncode == 0, accepted, run.stderr)

    def test_hazard_mutation_authentication_rejects_unrelated_edits(self):
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


if __name__ == "__main__":
    unittest.main()
