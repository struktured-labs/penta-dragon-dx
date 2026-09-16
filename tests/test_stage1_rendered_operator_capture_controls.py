#!/usr/bin/env python3
"""Offline controls for the supplemental real Stage-1 PNG regressions."""

from __future__ import annotations

import copy
import inspect
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts/diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import verify_stage1_rendered_continuity as continuity  # noqa: E402
import verify_stage1_reported_regressions_ready as ready  # noqa: E402


class RenderedOperatorCaptureControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture, cls.frames = continuity.load_operator_capture_controls()
        cls.specifications = {
            row["label"]: row for row in cls.fixture["captures"]
        }

    def test_fixture_adds_only_the_two_captures_not_owned_by_scene0b(self) -> None:
        self.assertEqual(
            set(self.specifications),
            {
                "operator-busted-room",
                "operator-official-room01-wall-edge",
            },
        )
        self.assertEqual(
            {
                row["path"] for row in self.fixture["captures"]
            },
            {
                "manual_captures/rc11_busted_room_2026_08_30.png",
                (
                    "manual_captures/"
                    "rc11_official_corrupted_wall_edges_2026_08_30.png"
                ),
            },
        )
        self.assertEqual(
            continuity.sha256(continuity.OPERATOR_CAPTURE_FIXTURE),
            continuity.OPERATOR_CAPTURE_FIXTURE_SHA256,
        )

    def test_every_supplemental_png_is_file_and_rgb_hash_pinned(self) -> None:
        for label, specification in self.specifications.items():
            with self.subTest(label=label):
                frame = self.frames[label]
                self.assertEqual(
                    continuity.sha256(frame.path), specification["sha256"]
                )
                rgb = bytes(
                    channel for color in frame.pixels for channel in color
                )
                self.assertEqual(
                    continuity.digest_bytes(rgb), specification["rgb_sha256"]
                )

    def test_busted_room_real_clear_cells_are_rejected(self) -> None:
        label = "operator-busted-room"
        frame = self.frames[label]
        specification = self.specifications[label]
        self.assertEqual(
            continuity.clear_hazard_cells(frame),
            [
                tuple(cell)
                for cell in specification["expected_clear_hazard_cells"]
            ],
        )
        count, failures = continuity.clear_cell_frames([frame])
        self.assertEqual(count, 1)
        self.assertEqual(failures, [frame.number])

    def test_official_room01_mixed_wall_ramp_is_rejected(self) -> None:
        label = "operator-official-room01-wall-edge"
        specification = self.specifications[label]
        result = continuity.reviewed_wall_palette_continuity(
            self.frames[label], specification["reviewed_wall_regions"]
        )
        self.assertEqual(
            (result["region_pixels"], result["region_mask_sha256"]),
            (
                specification["region_mask_pixels"],
                specification["region_mask_sha256"],
            ),
        )
        for prefix in ("bg0", "bg6"):
            expected = specification[f"{prefix}_dark"]
            self.assertEqual(result[f"{prefix}_dark_pixels"], expected["pixels"])
            self.assertEqual(
                result[f"{prefix}_dark_mask_sha256"],
                expected["mask_sha256"],
            )
        self.assertTrue(result["mixed_bg0_bg6"])
        self.assertFalse(result["exact_bg6_wall"])

    def test_capture_hash_drift_fails_closed_before_pixel_analysis(self) -> None:
        (ROOT / "tmp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="rendered-operator-control-", dir=ROOT / "tmp"
        ) as temporary:
            source = self.frames["operator-busted-room"].path
            mutated = Path(temporary) / "mutated.png"
            with Image.open(source) as image:
                changed = image.convert("RGB")
            changed.putpixel((0, 0), (1, 2, 3))
            changed.save(mutated)
            specification = copy.deepcopy(
                self.specifications["operator-busted-room"]
            )
            specification["path"] = str(mutated.relative_to(ROOT))
            with self.assertRaisesRegex(
                continuity.VerificationError,
                "operator rendered capture hash changed",
            ):
                continuity.load_pinned_operator_frame(specification)

    def test_archived_pixels_never_define_candidate_expected_output(self) -> None:
        self.assertNotIn(
            "operator_capture",
            inspect.getsource(continuity.analyze),
        )
        self.assertEqual(
            list(inspect.signature(
                continuity.reviewed_wall_palette_continuity
            ).parameters),
            ["frame", "rectangles"],
        )
        source = inspect.getsource(
            continuity.reviewed_wall_palette_continuity
        )
        self.assertIn("(82, 82, 123)", source)
        self.assertIn("(66, 66, 123)", source)
        self.assertNotIn("candidate", source.split('"""')[-1])

    def test_full_mutation_control_set_includes_real_png_controls(self) -> None:
        controls = continuity.mutation_controls()
        real_control_names = {
            "supplemental_operator_pngs_are_file_and_rgb_hash_pinned",
            "real_busted_room_clear_hazard_cells_match_reviewed_fixture",
            "real_busted_room_is_rejected_by_generic_clear_classifier",
            "real_official_wall_masks_match_reviewed_fixture",
            "real_official_mixed_room01_wall_ramp_is_rejected",
        }
        self.assertTrue(real_control_names <= ready.CONTINUITY_MUTATION_CONTROLS)
        for name in real_control_names:
            with self.subTest(control=name):
                self.assertIs(controls[name], True)

    def test_ready_validator_rehashes_the_supplemental_fixture(self) -> None:
        self.assertEqual(
            ready.CONTINUITY_OPERATOR_CAPTURE_FIXTURE,
            continuity.OPERATOR_CAPTURE_FIXTURE,
        )
        source = inspect.getsource(ready.validate_continuity_receipt)
        self.assertIn("sha256(CONTINUITY_OPERATOR_CAPTURE_FIXTURE)", source)
        self.assertIn(
            '"supplemental_operator_capture_fixture_sha256"', source
        )
        identity = ready.tool_identity()
        sealed = identity["rendered_continuity_operator_capture_fixture"]
        self.assertEqual(
            Path(sealed["path"]), ready.CONTINUITY_OPERATOR_CAPTURE_FIXTURE
        )
        self.assertEqual(
            sealed["sha256"],
            ready.sha256(ready.CONTINUITY_OPERATOR_CAPTURE_FIXTURE),
        )


if __name__ == "__main__":
    unittest.main()
