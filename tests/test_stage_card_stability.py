from __future__ import annotations

from pathlib import Path
import ast
import copy
import json
import sys
import tempfile
import unittest
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "diagnostics"))

import verify_stage_card_stability as stage_card  # noqa: E402


class StageCardExactPaletteTests(unittest.TestCase):
    def test_exact_single_run_is_accepted(self) -> None:
        segment = {
            "frames": 8,
            "first_frame": 341,
            "last_frame": 348,
            "bg0_runs": [{
                "first_frame": 341,
                "last_frame": 348,
                "value": "FF7FE07F803D0000",
            }],
        }
        self.assertTrue(stage_card.segment_uses_exact_bg0(
            segment, "FF7FE07F803D0000"
        ))

    def test_stable_wrong_color_is_rejected(self) -> None:
        segment = {
            "frames": 8,
            "first_frame": 341,
            "last_frame": 348,
            "bg0_runs": [{
                "first_frame": 341,
                "last_frame": 348,
                "value": "FF7F1F7C10000000",
            }],
        }
        self.assertFalse(stage_card.segment_uses_exact_bg0(
            segment, "FF7FE07F803D0000"
        ))

    def test_readiness_consumers_require_new_pixel_checks(self):
        import verify_stage1_reported_regressions_ready as ready
        import verify_pocket_visual_receipts as pocket
        tree = ast.parse(Path(stage_card.__file__).read_text())
        dictionaries = [node.value for node in ast.walk(tree)
                        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict)
                        and any(isinstance(target, ast.Name) and target.id == "checks"
                                for target in node.targets)]
        self.assertEqual(len(dictionaries), 1)
        checks = {ast.literal_eval(key): True for key in dictionaries[0].keys}
        self.assertEqual(set(checks), ready.STAGE_CARD_CHECKS)
        self.assertLessEqual(set(pocket.STAGE_CARD_CHECKS), set(checks))
        required = (
            "rendered STAGE card retires without exposing overwritten glyph graphics",
            "outgoing title never becomes a nonuniform monochrome image",
            "splash keeps the reviewed colored card or a raster-verified terminal black fade",
            "blank-SRAM splash keeps the reviewed card or raster-verified terminal black",
        )
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as scratch:
            path = Path(scratch) / "receipt.json"
            receipt = dict(schema=stage_card.SCHEMA, status="pass", observe_only=False,
                           rom_sha256="a" * 64, expected_title_bg0="FF7FE07F803D0000",
                           checks=checks)
            path.write_text(json.dumps(receipt))
            self.assertTrue(ready.validate_stage_card_receipt(path, "a" * 64)["all_checks_passed"])
            failures = []
            pocket.validate_stage_card_receipt(receipt, "a" * 64, failures)
            self.assertFalse(failures)
            for key in required:
                for missing in (False, True):
                    mutant = copy.deepcopy(receipt)
                    if missing:
                        del mutant["checks"][key]
                    else:
                        mutant["checks"][key] = False
                    path.write_text(json.dumps(mutant))
                    with self.assertRaises(ready.NotReady):
                        ready.validate_stage_card_receipt(path, "a" * 64)
                    failures = []
                    pocket.validate_stage_card_receipt(mutant, "a" * 64, failures)
                    self.assertTrue(failures)


class TitleExitColorTests(unittest.TestCase):
    @staticmethod
    def row(frame, *, scene="00", tiles="TITLE", chromatic=1000, colors=7, lcdc="83"):
        return {"frame": str(frame), "d880": scene, "tiles": tiles, "lcdc": lcdc,
                "visual": {"chromatic_pixels": chromatic, "distinct_colors": colors}}

    def clean(self):
        return [self.row(193, scene="01"), self.row(194, scene="01"),
                self.row(195, chromatic=0, colors=1, lcdc="00"),
                self.row(196), self.row(197, tiles="NEXT")]

    def test_colored_outgoing_title_and_uniform_blank_are_allowed(self):
        self.assertTrue(stage_card.title_exit_color_integrity(self.clean())["passed"])
        rows = self.clean()
        rows[3] = self.row(196, chromatic=0, colors=1)
        self.assertTrue(stage_card.title_exit_color_integrity(rows)["passed"])

    def test_monochrome_title_after_scene_change_is_rejected(self):
        rows = self.clean()
        rows[3] = self.row(196, chromatic=0, colors=2)
        result = stage_card.title_exit_color_integrity(rows)
        self.assertFalse(result["passed"])
        self.assertEqual(result["monochrome_frames"], [196])

    def test_missing_intermediate_frame_is_rejected(self):
        rows = self.clean()
        del rows[3]
        self.assertEqual(stage_card.title_exit_color_integrity(rows)["reason"],
                         "missing-transition-frame")

    def test_missing_baseline_or_replacement_is_rejected(self):
        self.assertFalse(stage_card.title_exit_color_integrity([])["passed"])
        self.assertFalse(stage_card.title_exit_color_integrity(self.clean()[:-1])["passed"])


class StageCardRetirementTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.addCleanup(self.scratch.cleanup)
        self.path = Path(self.scratch.name)
        self.palette = "FF7FE07F803D0000"
        self.rows = []
        for frame in range(10, 17):
            filename = f"frame-{frame:04d}.png"
            Image.new("RGB", (160, 144), "black").save(self.path / filename)
            self.rows.append(dict(frame=str(frame), d880="18" if frame < 16 else "02",
                                  tiles="CARD" if frame < 16 else "DUNGEON",
                                  bg0=self.palette if frame < 14 else "0000000000000000",
                                  screenshot=filename, visual={"chromatic_pixels": 100}))

    def check(self):
        return stage_card.stage_card_palette_retirement(self.rows, self.path, self.palette)

    def test_reviewed_card_then_exact_terminal_black_passes(self):
        result = self.check()
        self.assertTrue(result["passed"])
        self.assertEqual(result["terminal_black_frames"], [14, 15])

    def test_nonblank_raster_with_black_cram_is_rejected(self):
        image = Image.new("RGB", (160, 144), "black")
        image.putpixel((0, 0), (255, 0, 0))
        image.save(self.path / "frame-0014.png")
        self.assertFalse(self.check()["passed"])

    def test_card_reappearance_and_third_palette_are_rejected(self):
        for palette in (self.palette, "FF7FFF7FFF7FFF7F", "FF7F1F7C10000000"):
            self.rows[5]["bg0"] = palette
            self.assertFalse(self.check()["passed"])

    def test_monochrome_lettering_is_not_a_blank_fade(self):
        self.rows[2]["visual"]["chromatic_pixels"] = 0
        self.assertFalse(self.check()["passed"])

    def test_black_from_the_start_is_rejected(self):
        for row in self.rows:
            row["bg0"] = "0000000000000000"
        self.assertFalse(self.check()["passed"])

    def test_missing_frame_or_dungeon_replacement_is_rejected(self):
        rows = self.rows.copy()
        del self.rows[2]
        self.assertFalse(self.check()["passed"])
        self.rows = rows[:-1]
        self.assertFalse(self.check()["passed"])


class StageCardRasterTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.addCleanup(self.scratch.cleanup)
        self.path = Path(self.scratch.name)
        self.card = Image.new("RGB", (160, 144), "black")
        draw = ImageDraw.Draw(self.card)
        draw.rectangle((16, 32, 31, 47), fill=(0, 255, 255))
        draw.rectangle((20, 36, 27, 43), fill="white")
        tiles = bytearray(360)
        tiles[82] = 0x6E
        self.rows = []
        for frame in range(100, 113):
            filename = f"frame-{frame:04d}.png"
            self.card.save(self.path / filename)
            self.rows.append({"frame":str(frame), "d880":"18" if frame < 112 else "02",
                              "tiles":tiles.hex() if frame < 112 else bytes([1]*360).hex(),
                              "tile_hash":"UNCHANGED", "screenshot":filename})

    def check(self):
        return stage_card.stage_card_raster_integrity(self.rows, self.path)

    def test_intact_card_and_uniform_retirement_pass(self):
        self.assertTrue(self.check()["passed"])
        Image.new("RGB", (160, 144), "white").save(self.path / "frame-0110.png")
        Image.new("RGB", (160, 144), "black").save(self.path / "frame-0111.png")
        result = self.check()
        self.assertTrue(result["passed"])
        self.assertEqual(result["uniform_blank_frames"], [110, 111])

    def test_global_palette_remap_does_not_change_geometry(self):
        remap = {(0,0,0):(8,8,32), (0,255,255):(255,255,0), (255,255,255):(255,200,100)}
        changed = self.card.copy()
        changed.putdata([remap[p] for p in self.card.getdata()])
        changed.save(self.path / "frame-0110.png")
        self.assertTrue(self.check()["passed"])

    def test_one_glyph_pixel_fails_despite_unchanged_tilemap(self):
        changed = self.card.copy()
        changed.putpixel((18, 34), (255, 0, 0))
        changed.save(self.path / "frame-0110.png")
        result = self.check()
        self.assertFalse(result["passed"])
        self.assertEqual([r["frame"] for r in result["unexpected_frames"]], [110])
        self.assertTrue(result["unexpected_frames"][0]["tilemap_unchanged"])

    def test_partial_background_retirement_fails(self):
        changed = self.card.copy()
        ImageDraw.Draw(changed).rectangle((0, 0, 159, 24), fill="white")
        changed.save(self.path / "frame-0110.png")
        self.assertFalse(self.check()["passed"])

    def test_late_corrupted_frames_cannot_become_the_reference(self):
        changed = self.card.copy()
        changed.putpixel((18, 34), (255, 0, 0))
        for frame in range(104, 112):
            changed.save(self.path / f"frame-{frame:04d}.png")
        result = self.check()
        self.assertEqual(result["reference_frame"], 100)
        self.assertEqual(len(result["unexpected_frames"]), 8)
        self.assertFalse(result["passed"])

    def test_missing_frame_and_missing_visible_baseline_fail(self):
        self.rows = [r for r in self.rows if r["frame"] != "108"]
        self.assertEqual(self.check()["reason"], "missing-transition-frame")
        for row in self.rows:
            Image.new("RGB", (160, 144), "white").save(self.path / row["screenshot"])
        self.assertEqual(self.check()["reason"], "missing-stable-early-card-raster")


if __name__ == "__main__":
    unittest.main()
