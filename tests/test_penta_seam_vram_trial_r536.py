import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))
import build_penta_seam_vram_trial_r536 as trial
import build_stage_card_blank_trial_r535 as stage_card
import build_title_tile_retire_trial_r535 as title


class PentaSeamVramTrialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = stage_card.build(title.build(
            (ROOT / "tmp/stage4-cache-key-r534/candidate.gb").read_bytes()
        ))

    def test_deterministic_exact_parent_and_checksum(self):
        self.assertEqual(hashlib.sha256(self.source).hexdigest(), trial.BASE_SHA)
        result = trial.build(self.source)
        self.assertEqual(hashlib.sha256(result).hexdigest(),
                         "b93ebc46ed4ac23ec7d2c44d80fae1ae1538b38c038bab0ba8173b93fe252350")
        self.assertEqual(result, trial.build(self.source))
        self.assertEqual(result[0x14E:0x150],
                         ((sum(result[:0x14E]) + sum(result[0x150:])) & 0xFFFF).to_bytes(2, "big"))

    def test_only_owned_stub_cave_and_checksum_change(self):
        stub, helper = trial.payloads()
        owned = {0x14E, 0x14F} | set(range(trial.HOOK, trial.HOOK + len(stub)))
        owned |= set(range(trial.HELPER, trial.HELPER + len(helper)))
        result = trial.build(self.source)
        differences = {i for i, (a, b) in enumerate(zip(self.source, result, strict=True)) if a != b}
        self.assertLessEqual(differences, owned)
        # Original scene discrimination and VBK/lava-dispatch tail survive.
        for start, end in ((trial.HOOK - 8, trial.HOOK), (trial.HOOK + 17, trial.HOOK + 23)):
            self.assertEqual(result[start:end], self.source[start:end])

    def test_both_vram_accesses_have_independent_mode_waits(self):
        _, helper = trial.payloads()
        self.assertEqual(helper.count(trial.WAIT), 2)
        self.assertIn(trial.WAIT + bytes.fromhex("7E 6F 26 C6 7E 47"), helper)
        self.assertIn(trial.WAIT + bytes.fromhex("70"), helper)
        # No DI/EI or replacement palette constant: the current LUT owns B.
        self.assertNotIn(0xF3, helper)
        self.assertNotIn(0xFB, helper)

    def test_mapper_returns_through_retained_bank13_tail(self):
        stub, helper = trial.payloads()
        self.assertEqual(stub[:13], bytes.fromhex("21 45 57 E5 21 50 62 E5 3E 14 C3 61 00"))
        self.assertTrue(helper.endswith(bytes.fromhex("70 3E 0D C3 61 00")))

    def test_source_mutations_fail_closed(self):
        for offset in (trial.HOOK, trial.HELPER, 0x14F, 0x100, trial.HELPER - 1):
            source = bytearray(self.source)
            source[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                trial.build(source)

    def test_full_bank_owner_reconstruction_and_mutations(self):
        from arena_bank20_r455 import matches, visible_seam_matches, expected_penta_seam_bank20
        result = trial.build(self.source)
        self.assertEqual(result[20 * 0x4000:21 * 0x4000], expected_penta_seam_bank20())
        self.assertTrue(matches(result))
        self.assertTrue(visible_seam_matches(result))
        self.assertTrue(visible_seam_matches(self.source))
        for offset in (trial.HELPER, trial.HELPER - 1, trial.HOOK):
            mutated = bytearray(result)
            mutated[offset] ^= 1
            with self.subTest(offset=offset):
                self.assertFalse(matches(mutated))
                self.assertFalse(visible_seam_matches(mutated))

    def test_inherited_observers_keep_exact_guards(self):
        from stage_card_palette_handoff import inspect_stage_card_palette_handoff
        from arena_palette_storage import arena_palette_table
        from generate_stream_boss_states import relocated_ted_latches
        from verify_menu_icon_palettes import menu_oracle
        from verify_stage1_no_bleed import expected_stage1_table
        from verify_stage1_pickup_art import expected_stage1_table as pickup_table
        from verify_low_health_flicker import publication_route_profile, owner_address, bulk_compiler_profile
        from verify_stage1_spike_palettes import publication_boundary, semantic_expansion_is_exact
        result = trial.build(self.source)
        self.assertTrue(inspect_stage_card_palette_handoff(result)["installed"])
        for probe in (relocated_ted_latches, menu_oracle, expected_stage1_table,
                      pickup_table, publication_route_profile, owner_address, bulk_compiler_profile):
            with self.subTest(probe=probe.__module__ + "." + probe.__name__):
                self.assertEqual(probe(result), probe(self.source))
        for target in range(9):
            self.assertEqual(arena_palette_table(result, target), arena_palette_table(self.source, target))
        self.assertTrue(semantic_expansion_is_exact(result))
        self.assertEqual(publication_boundary(result)["pc"], 0x7457)
        for offset in (0x14F, 0x12E0, 0x37000):
            changed = bytearray(result)
            changed[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(RuntimeError):
                publication_boundary(changed)

    def test_atomic_contract_accepts_repair_and_rejects_mutations(self):
        from verify_boss_atomic_attr_contract import verify
        import contextlib
        import io

        result = trial.build(self.source)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(verify(self.source), 0)
            self.assertEqual(verify(result), 0)
        for offset in (trial.HOOK - 1, trial.HOOK, trial.HOOK + 17,
                       trial.HELPER - 1, trial.HELPER, trial.HELPER + 33):
            mutated = bytearray(result)
            mutated[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(AssertionError):
                verify(mutated)

    def test_current_hazard_fixture_is_required(self):
        from verify_release_candidate import build_gates
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as scratch:
            path = Path(scratch) / "candidate.gb"
            path.write_bytes(trial.build(self.source))
            gates = {gate.name: gate for gate in build_gates(path, Path(scratch) / "matrix")}
            self.assertEqual(gates["low_health_flicker"].dependencies, ("stage1_current_hazard_state",))
            self.assertIn("--boot-derived-state", gates["low_health_flicker"].command)

    def test_lua_publisher_profile_keeps_name_and_opcode_guards(self):
        lua = shutil.which("lua")
        if lua is None:
            self.skipTest("standalone Lua interpreter unavailable")
        source = (ROOT / "scripts/diagnostics/probe_stage1_spike_palettes.lua").read_text()
        prefix = source[source.index("PENTA_PRIMARY_ADDR ="):
                        source.index('if watchdog then watchdog:write("init:publication-match')]
        body = trial.build(self.source)[0x12E0:0x1303]
        for name, payload, accepted in (
                ("r536-penta-seam-vram-b93ebc46", body, True),
                ("unknown-rom", body, False),
                ("r536-penta-seam-vram-b93ebc46", bytes([body[0] ^ 1]) + body[1:], False)):
            setup = (f"PENTA_EXPECTED_PUBLICATION_VARIANT={json.dumps(name)}\n"
                     f"local payload=string.char({','.join(map(str, payload))})\n"
                     "emu={read8=function(self,address) return assert(payload:byte(address-0x12E0+1)) end}\n")
            run = subprocess.run([lua, "-"], input=setup + prefix, text=True,
                                 capture_output=True, timeout=5)
            self.assertEqual(run.returncode == 0, accepted, run.stderr)


if __name__ == "__main__":
    unittest.main()
