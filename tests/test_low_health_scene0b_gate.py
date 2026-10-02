from __future__ import annotations

from pathlib import Path
import importlib.util
import unittest


ROOT = Path(__file__).resolve().parents[1]


class LowHealthScene0BGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.probe = (
            ROOT / "scripts/diagnostics/probe_low_health_flicker.lua"
        ).read_text()
        self.verifier = (
            ROOT / "scripts/diagnostics/verify_low_health_flicker.py"
        ).read_text()
        self.determinism = (
            ROOT / "scripts/diagnostics/verify_low_health_hazard_determinism.py"
        ).read_text()
        self.release = (
            ROOT / "scripts/diagnostics/verify_release_candidate.py"
        ).read_text()
        spec = importlib.util.spec_from_file_location(
            "verify_low_health_flicker",
            ROOT / "scripts/diagnostics/verify_low_health_flicker.py",
        )
        assert spec is not None and spec.loader is not None
        self.verifier_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.verifier_module)

    def test_probe_drives_only_the_native_health_source(self) -> None:
        self.assertIn("local SCENE0B_HEALTH = 0x40", self.probe)
        self.assertIn(
            "native_assistance.write(0xDCBB, SCENE0B_HEALTH)", self.probe
        )
        self.assertIn("native_assistance.write(0xDCBB, 0xFF)", self.probe)
        self.assertNotIn("emu:write8(0xDCBB", self.probe)  # #41 physical bank1
        self.assertNotIn("emu:write8(0xDD06", self.probe)
        self.assertNotIn("emu:write8(0xD880", self.probe)
        self.assertIn(r"\troom\tffe5\tscy", self.probe)
        self.assertIn(r"\tstimulus_phase\tdcbb\tdd06\tffb7\tffbf\tffba", self.probe)

    def test_scanner_records_exact_room_commit_lcd_phase(self) -> None:
        self.assertIn(
            r"\tscene\troom\tffe5\tdc0b\tdc0e\tvbk\tly\tstat\tlcdc\tffe0",
            self.probe,
        )
        self.assertIn('trace_scanner("room-hook", "room")', self.probe)
        self.assertIn("0x6C80, 21", self.probe)

    def test_ordinary_oracle_is_owned_by_completed_physical_publication(
        self,
    ) -> None:
        self.assertIn("published_expected_planes", self.probe)
        self.assertIn(
            "setBreakpoint(inspect_resident_compiler_row, 0x4313, 1) > 0",
            self.probe,
        )
        self.assertIn(
            "setBreakpoint(publish_expected_plane, 0x4354, 1) > 0",
            self.probe,
        )
        self.assertIn("emu:read8(0xFF55) ~= 0xFF", self.probe)
        receipt = self.probe.split(
            "local function visible_bg_receipt()", 1
        )[1].split("local function resident_runtime()", 1)[0]
        self.assertIn("publication.expected[offset]", receipt)
        self.assertNotIn("emu:read8(0xC600", receipt)
        self.assertIn(
            '"every rendered map uses a completed publication-owned oracle"',
            self.verifier,
        )

    def test_room_register_handoff_keeps_physical_owner_epoch(self) -> None:
        base = {
            "sample": "187",
            "room": "01",
            "map": "9800",
            "tile_bytes": "AA",
            "attr_bytes": "BB",
            "map_owner_valid": "1",
            "map_owner_epoch": "40",
            "unexpected_mismatches": "0",
        }
        changed = dict(base, sample="188", room="05")
        helper = self.verifier_module.publication_owner_handoffs
        observed = helper([base, changed])
        self.assertTrue(observed["exact"])
        self.assertEqual(observed["count"], 1)
        stale = dict(changed, map_owner_epoch="41")
        self.assertFalse(helper([base, stale])["exact"])

    def test_warning_window_keeps_a_clean_pre_and_recovery_phase(self) -> None:
        self.assertIn('stimulus_phase = "pre"', self.probe)
        self.assertIn('stimulus_phase = "scene0b"', self.probe)
        self.assertIn('stimulus_phase = "recovered"', self.probe)
        self.assertIn(
            '"native evaluator orders healthy -> DD06 -> scene $0B"',
            self.verifier,
        )
        self.assertIn(
            '"bounded DCBB-only stimulus recovers through native state"',
            self.verifier,
        )
        self.assertIn(
            "drive_publication = scene0b_postcopy_hits == 0", self.probe
        )
        self.assertLess(
            self.probe.index(
                "drive_publication = scene0b_postcopy_hits == 0"
            ),
            self.probe.index("emu:setKeys("),
        )

    def test_candidate_runtime_is_checked_before_trigger(self) -> None:
        self.assertIn("bind_candidate_runtime()", self.probe)
        self.assertLess(
            self.probe.index("bind_candidate_runtime()"),
            self.probe.index("native_assistance.write(0xDCBB, SCENE0B_HEALTH)"),
        )
        self.assertIn("STAGE1_RUNTIME_SOURCE_OFFSETS", self.verifier)
        self.assertIn(
            '"resident DAD7 helper matches an exact candidate source"',
            self.verifier,
        )
        self.assertIn("resident_runtime_matches_candidate()", self.probe)
        self.assertIn("runtime_scene0b_entry_mismatches", self.probe)

    def test_low_health_route_has_bank_qualified_owners(self) -> None:
        self.assertIn("end, 0xDAD7) > 0", self.probe)
        self.assertIn("end, 0x4100, 21) > 0", self.probe)
        for counter in (
            "scene0b_postcopy", "scene0b_dispatch", "scene0b_front",
            "scene0b_write", "split_consumer_scene0b",
        ):
            self.assertIn(counter, self.probe)
            self.assertIn(counter, self.verifier)

    def test_scene_authority_and_visual_checks_are_hard_failures(self) -> None:
        for text in (
            "native evaluator orders healthy -> DD06 -> scene $0B",
            "scene-$0B window retains exact Stage-1 authority",
            "scene-$0B publications reach the hazard dispatcher",
            "scene-$0B reaches the semantic row writer",
            "atomic copier receives an exact physical BG-map destination",
            "map-done consumes only exact even/odd destination tags",
            "scene-$0B dirty decision preserves physical destination H",
            "scene-$0B dirty decision reaches exact tagged map-done",
            "healthy pre-stimulus hazard oracle is already clean",
        ):
            self.assertIn(text, self.verifier)

    def test_latch_probe_observes_decision_before_postcopy_cleanup(self) -> None:
        self.assertIn("end, 0x42ED, 1)", self.probe)
        self.assertIn('early_register("hl") >> 8', self.probe)
        self.assertIn("scene0b_atomic_setup_invalid_h", self.probe)
        self.assertIn("scene0b_mapdone_invalid_latch", self.probe)
        self.assertIn("end, 0x4500, 20)", self.probe)

    def test_ffe5_hypothesis_is_recorded_but_not_a_release_gate(self) -> None:
        receipt = self.verifier_module.ffe5_room01_observation([
            {"sample": "73", "room": "12", "ffe5": "01"},
            {"sample": "74", "room": "12", "ffe5": "01"},
            {"sample": "75", "room": "01", "ffe5": "01"},
            {"sample": "76", "room": "01", "ffe5": "01"},
        ])
        self.assertTrue(receipt["supports_prepublication_selector"])
        self.assertEqual(receipt["precommit_samples"], [73, 74])
        self.assertNotIn(
            '"effective room key precedes and matches room-$01 commit":',
            self.verifier,
        )

    def test_rejected_ffe5_observation_stays_explicit(self) -> None:
        helper = self.verifier_module.ffe5_room01_observation
        observed = helper([
            {"sample": "74", "room": "12", "ffe5": "12"},
            {"sample": "75", "room": "01", "ffe5": "01"},
        ])
        self.assertFalse(observed["supports_prepublication_selector"])
        self.assertIn('"ffe5_room01_observation"', self.verifier)

    def test_resident_d400_compiler_is_breakpoint_bound_and_fail_closed(self) -> None:
        self.assertIn(
            "setBreakpoint(arm_resident_compiler_receipt, 0x4302, 1) > 0",
            self.probe,
        )
        self.assertIn(
            "setBreakpoint(inspect_resident_compiler_row, 0x4313, 1) > 0",
            self.probe,
        )
        self.assertIn("EXPECTED_D400", self.probe)
        self.assertIn("de == 0xC1A0 + row * 0x18", self.probe)
        self.assertIn("hl == 0xD000 + row * 0x20", self.probe)
        self.assertNotIn("hl == 0xD000 + row * 0x18", self.probe)
        self.assertNotIn("emu:write8(0xFF70", self.probe)
        helper = self.verifier_module.resident_compiler_counter_contract
        known_good = {
            "compiler_publications": 2,
            "compiler_first_rows": 2,
            "compiler_row_calls": 48,
            "compiler_contract_mismatches": 0,
        }
        self.assertTrue(helper(known_good))
        for key, value in (
            ("compiler_row_calls", 47),
            ("compiler_first_rows", 1),
            ("compiler_contract_mismatches", 1),
        ):
            mutant = dict(known_good)
            mutant[key] = value
            with self.subTest(key=key):
                self.assertFalse(helper(mutant))

    def test_final_settle_rebind_is_tooth_only_and_receipted(self) -> None:
        function = self.probe.split(
            "local function bind_cross_rom_fixture_hazards()", 1
        )[1].split("local function visible_bg_receipt()", 1)[0]
        self.assertIn("positions", function)
        self.assertIn("folded >= 0x64 and folded < 0x6A", function)
        self.assertIn('emu:write8(base + offset, 0x0F)', function)
        self.assertNotIn("0xC600", function)
        self.assertIn(".fixture-tooth-rebind.txt", function)
        self.assertIn("live_fixture_tooth_only_rebind", self.verifier)

    def test_determinism_wrapper_and_release_gate_forward_profile(self) -> None:
        self.assertIn("--require-scene0b-low-health", self.determinism)
        self.assertIn("--scene0b-frames", self.determinism)
        self.assertIn('"low_health_scene0b_publication"', self.release)
        self.assertIn('"low-health-scene0b-publication"', self.release)


if __name__ == "__main__":
    unittest.main()
