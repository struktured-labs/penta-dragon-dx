from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import verify_stage1_natural_menu_bg as menu_gate  # noqa: E402


class NaturalMenuFullFrameGateTests(unittest.TestCase):
    def setUp(self) -> None:
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(
            prefix="natural-menu-full-frame-", dir=ROOT / "tmp"
        )
        self.root = Path(self.temp.name)
        self.clean = self.root / "clean.png"
        image = Image.new("RGB", (160, 144), (255, 255, 255))
        pixels = image.load()
        for y in range(144):
            for x in range(160):
                if (x + y) % 8 == 0:
                    pixels[x, y] = (165, 165, 255)
        image.save(self.clean)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_r534_publication_breakpoint_uses_authenticated_bank_13(self) -> None:
        rom = (ROOT / "tmp/stage4-cache-key-r534/candidate.gb").read_bytes()
        publication = menu_gate.detect_publication_boundary(rom)
        self.assertEqual(publication["variant"],
                         "r534-stage4-cache-key-727ee496")
        self.assertEqual(publication["publication_pc_hex"], "7457")
        self.assertEqual(publication["publication_segment_hex"], "0D")

    def report(
        self, post: Path, *, baseline_oam: str = "", post_oam: str = ""
    ) -> dict[str, str]:
        entries = [
            f"f{frame}:h8:sAABB:o{baseline_oam}:p{self.clean}"
            for frame in range(600, 1200)
        ]
        entries.extend(
            f"f{frame}:h8:sAABB:o{post_oam}:p{post}"
            for frame in range(1382, 1442)
        )
        return {
            "raster_baseline_frames": "600",
            "temporal_raster_trace": ";".join(entries),
        }

    def mutated_image(
        self, name: str, rectangle: tuple[int, int, int, int]
    ) -> Path:
        with Image.open(self.clean) as source:
            image = source.convert("RGB")
        left, top, right, bottom = rectangle
        pixels = image.load()
        for y in range(top, bottom):
            for x in range(left, right):
                pixels[x, y] = (0, 0, 255)
        path = self.root / name
        image.save(path)
        return path

    def test_clean_full_frame_and_oam_phase_pass(self) -> None:
        receipt = menu_gate.temporal_raster_receipt(
            self.report(self.clean), 1200, 1380
        )
        self.assertTrue(receipt["enabled"])
        self.assertEqual(receipt["raster_height"], 144)
        self.assertEqual(receipt["mismatch_frames"], 0)
        self.assertEqual(receipt["unmatched_oam_phase_frames"], 0)
        self.assertTrue(menu_gate.projectile_observation_is_safe(receipt))
        # The absence exception cannot hide another unknown sprite slot.
        receipt["visible_unknown_oam_frames"] = 1
        self.assertFalse(menu_gate.projectile_observation_is_safe(receipt))

    def test_upper_left_red_green_splatter_after_close_is_rejected(self) -> None:
        # Operator's r534 report: START, exit, no movement. The second START
        # was only to take a screenshot, not a prerequisite for the defect.
        # Exercise the full-frame oracle with independent clean background;
        # do not admit the photographed corruption as an allowed baseline.
        with Image.open(self.clean) as source:
            bad = source.convert("RGB")
        for y in range(40):
            for x in range(32):
                if (x + y) % 3 == 0:
                    bad.putpixel((x, y), (255, 0, 0) if x >= 16 else (0, 255, 0))
        path = self.root / "upper-left-red-green.png"
        bad.save(path)
        receipt = menu_gate.temporal_raster_receipt(self.report(path), 1200, 1380)
        self.assertEqual(receipt["checked_frames"], 60)
        self.assertEqual(receipt["full_frame_mismatch_frames"], 60)
        self.assertGreater(receipt["mismatch_frames"], 0)
        self.assertFalse(menu_gate.projectile_observation_is_safe(receipt))

    def test_full_release_and_live_rosters_require_captured_stationary_route(self) -> None:
        from verify_release_candidate import build_gates
        from verify_live_regression import LIVE_GATES
        rom = ROOT / "tmp/stage4-cache-key-r534/candidate.gb"
        gates = build_gates(rom, self.root / "matrix")
        matches = [g for g in gates if g.name == "stage1_captured_menu_stationary"]
        self.assertEqual(len(matches), 1)
        command = matches[0].command
        self.assertIn("--operator-fixture", command)
        self.assertTrue(any(c.endswith("verify_stage1_captured_menu.py") for c in command))
        self.assertEqual(command[command.index("--close-key") + 1], "b")
        self.assertNotIn("--move", command)
        self.assertNotIn("--no-menu-control", command)
        self.assertIn("stage1_captured_menu_stationary", LIVE_GATES)

    def test_reallocated_enemy_requires_full_known_quad_and_rom_authentication(self):
        before = "8/72/24/55/24,9/80/24/54/24,10/72/32/57/24,11/80/32/56/24"
        after = "20/80/32/55/24,21/88/32/54/24,22/80/40/57/24,23/88/40/56/24"
        report = self.report(self.clean, baseline_oam=before, post_oam=after)
        unauthenticated = menu_gate.temporal_raster_receipt(report, 1200, 1380)
        self.assertGreater(unauthenticated["visible_unknown_oam_frames"], 0)
        valid = menu_gate.temporal_raster_receipt(
            report, 1200, 1380, obj_atlas_authenticated=True)
        self.assertEqual(valid["visible_unknown_oam_frames"], 0)
        self.assertEqual(valid["full_frame_mismatch_frames"], 0)
        mutations = [
            after.replace("55/24", "55/25"),  # changed palette
            after.replace("55/24", "55/A4"),  # changed priority
            after.replace("55/24", "59/24"),  # unknown animation
            after.replace("21/88/32", "21/89/32"),  # broken geometry
            after.rsplit(",", 1)[0],  # incomplete assembly
            after.replace("20/", "0/").replace("21/", "1/")
                 .replace("22/", "2/").replace("23/", "3/"),
        ]
        for changed in mutations:
            with self.subTest(changed=changed):
                result = menu_gate.temporal_raster_receipt(
                    self.report(self.clean, baseline_oam=before, post_oam=changed),
                    1200, 1380, obj_atlas_authenticated=True)
                self.assertGreater(result["visible_unknown_oam_frames"], 0)

    def test_known_projectile_motion_is_not_misclassified(self) -> None:
        # This is the exact 8x8 geometry captured by the operator on r364.
        # Slot 34/tile $0F predates SELECT and moves like the normal shot.
        artifact = self.mutated_image("sarah-oam-artifact.png", (69, 49, 77, 57))
        entries = [
            f"f{frame}:h8:sAABB:o34/{77 + (frame % 2) * 4}/65/0F/00:p{artifact}"
            for frame in range(600, 1200)
        ]
        entries.extend(
            f"f{frame}:h8:sAABB:o34/{77 + (frame % 2) * 4}/65/0F/00:p{artifact}"
            for frame in range(1382, 1442)
        )
        receipt = menu_gate.temporal_raster_receipt(
            {
                "raster_baseline_frames": "600",
                "temporal_raster_trace": ";".join(entries),
            },
            1200,
            1380,
        )
        self.assertEqual(receipt["unmatched_oam_phase_frames"], 0)
        self.assertEqual(receipt["full_frame_mismatch_frames"], 0)
        classification = receipt["operator_projectile_classification"]
        self.assertTrue(classification["predates_select"])
        self.assertTrue(classification["survives_roundtrip"])
        self.assertTrue(classification["moves"])
        self.assertTrue(classification["classified_as_moving_projectile"])
        self.assertTrue(menu_gate.projectile_observation_is_safe(receipt))

    def test_stationary_post_select_block_is_not_a_known_projectile(self) -> None:
        artifact = self.mutated_image("stationary-block.png", (69, 49, 77, 57))
        receipt = menu_gate.temporal_raster_receipt(
            self.report(artifact, post_oam="34/77/65/0F/00"),
            1200,
            1380,
        )
        classification = receipt["operator_projectile_classification"]
        self.assertFalse(classification["predates_select"])
        self.assertFalse(classification["moves"])
        self.assertFalse(classification["classified_as_moving_projectile"])
        self.assertFalse(menu_gate.projectile_observation_is_safe(receipt))

    def test_projectile_departed_before_menu_does_not_need_to_survive(self):
        report = self.report(self.clean)
        entries = report['temporal_raster_trace'].split(';')
        for i in range(20):
            entries[i] = entries[i].replace(':o:', f':o34/{80+i}/65/0F/00:')
        report['temporal_raster_trace'] = ';'.join(entries)
        receipt = menu_gate.temporal_raster_receipt(report,1200,1380)
        observed = receipt['operator_projectile_classification']
        self.assertTrue(observed['departed_before_select'])
        self.assertEqual(observed['last_baseline_frame'],619)
        self.assertFalse(observed['survives_roundtrip'])
        self.assertFalse(observed['classified_as_moving_projectile'])
        self.assertTrue(menu_gate.projectile_observation_is_safe(receipt))
        for key, bad in [('post_close_frames',1),('moves',False),('palette_indices',[2])]:
            old=observed[key];observed[key]=bad
            self.assertFalse(menu_gate.projectile_observation_is_safe(receipt))
            observed[key]=old
        receipt['visible_unknown_oam_frames']=1
        self.assertFalse(menu_gate.projectile_observation_is_safe(receipt))
        # Missing final pre-menu observation cannot establish departure.
        report['temporal_raster_trace']=';'.join(e for e in entries if not e.startswith('f1199:'))
        incomplete=menu_gate.temporal_raster_receipt(report,1200,1380)
        self.assertFalse(incomplete['operator_projectile_classification']['departed_before_select'])
        self.assertFalse(menu_gate.projectile_observation_is_safe(incomplete))

    def test_sarah_priority_floor_through_fails(self) -> None:
        receipt = menu_gate.temporal_raster_receipt(
            self.report(
                self.clean,
                baseline_oam="2/80/88/27/A2",
                post_oam="2/80/88/27/A2",
            ),
            1200,
            1380,
        )
        contract = receipt["sarah_priority_contract"]
        self.assertGreater(contract["oam_entries"], 0)
        self.assertEqual(contract["priority_frames"], 660)
        self.assertFalse(contract["passed"])

    def test_sarah_without_priority_passes(self) -> None:
        receipt = menu_gate.temporal_raster_receipt(
            self.report(
                self.clean,
                baseline_oam="2/80/88/27/22",
                post_oam="2/80/88/27/22",
            ),
            1200,
            1380,
        )
        contract = receipt["sarah_priority_contract"]
        self.assertGreater(contract["oam_entries"], 0)
        self.assertEqual(contract["priority_frames"], 0)
        self.assertTrue(contract["passed"])

    def test_cgb_ignored_sara_obp_bit_requires_obj_authentication(self) -> None:
        baseline = (
            "0/80/80/24/02,1/88/80/25/02,"
            "2/80/88/27/22,3/88/88/26/22"
        )
        post = (
            "0/80/80/24/12,1/88/80/25/12,"
            "2/80/88/27/32,3/88/88/26/32"
        )
        report = self.report(
            self.clean, baseline_oam=baseline, post_oam=post
        )
        unauthenticated = menu_gate.temporal_raster_receipt(
            report, 1200, 1380
        )
        self.assertEqual(unauthenticated["visible_unknown_oam_frames"], 60)

        authenticated = menu_gate.temporal_raster_receipt(
            report, 1200, 1380, obj_atlas_authenticated=True
        )
        self.assertEqual(authenticated["visible_unknown_oam_frames"], 0)
        self.assertEqual(authenticated["full_frame_mismatch_frames"], 0)

        # CGB-rendering flags remain fail closed; only ignored DMG OBP1 bit 4
        # is normalized for the independently authenticated Sara records.
        for changed in (
            post.replace("24/12", "24/32"),
            post.replace("24/12", "24/52"),
            post.replace("24/12", "24/92"),
            post.replace("24/12", "23/12"),
        ):
            with self.subTest(changed=changed):
                result = menu_gate.temporal_raster_receipt(
                    self.report(
                        self.clean,
                        baseline_oam=baseline,
                        post_oam=changed,
                    ),
                    1200,
                    1380,
                    obj_atlas_authenticated=True,
                )
                self.assertGreater(result["visible_unknown_oam_frames"], 0)

    def test_unseen_visible_post_menu_oam_identity_fails(self) -> None:
        receipt = menu_gate.temporal_raster_receipt(
            self.report(
                self.clean,
                baseline_oam="7/77/65/41/05",
                post_oam="7/77/65/42/05",
            ),
            1200,
            1380,
        )
        self.assertEqual(receipt["unmatched_oam_phase_frames"], 60)
        self.assertEqual(receipt["visible_unknown_oam_frames"], 60)
        self.assertEqual(receipt["mismatch_frames"], 60)

    def test_unseen_offscreen_post_menu_oam_identity_is_diagnostic(self) -> None:
        receipt = menu_gate.temporal_raster_receipt(
            self.report(
                self.clean,
                baseline_oam="7/77/8/41/05",
                post_oam="7/77/8/42/05",
            ),
            1200,
            1380,
        )
        self.assertEqual(receipt["unmatched_oam_phase_frames"], 60)
        self.assertEqual(receipt["visible_unknown_oam_frames"], 0)
        self.assertEqual(receipt["mismatch_frames"], 0)

    def test_bottom_band_repetition_is_inside_the_oracle(self) -> None:
        artifact = self.mutated_image(
            "bottom-band-artifact.png", (16, 128, 144, 144)
        )
        receipt = menu_gate.temporal_raster_receipt(
            self.report(artifact), 1200, 1380
        )
        self.assertEqual(receipt["full_frame_mismatch_frames"], 60)
        self.assertEqual(
            receipt["first_full_frame_mismatch"]["first_xy"], [16, 128]
        )

    def test_music_gate_checks_rate_and_single_frame_continuity(self) -> None:
        report = {
            "timer_isr_hits": "625",
            "timer_baseline_hits": "178",
            "timer_menu_hits": "269",
            "timer_post_close_hits": "178",
            "timer_max_frame_gap": "1",
        }
        receipt = menu_gate.timer_cadence_receipt(report, 1500, 1200, 1380)
        self.assertTrue(receipt["passed"])

        slow = dict(report)
        slow["timer_isr_hits"] = "617"
        slow["timer_post_close_hits"] = "170"
        self.assertFalse(
            menu_gate.timer_cadence_receipt(slow, 1500, 1200, 1380)[
                "passed"
            ]
        )

        skipped = dict(report)
        skipped["timer_max_frame_gap"] = "2"
        self.assertFalse(
            menu_gate.timer_cadence_receipt(skipped, 1500, 1200, 1380)[
                "passed"
            ]
        )


if __name__ == "__main__":
    unittest.main()
