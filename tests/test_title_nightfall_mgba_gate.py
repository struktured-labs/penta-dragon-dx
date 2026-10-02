from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import build_stage1_title_nightfall_r366 as r366  # noqa: E402
import verify_title_nightfall_mgba as gate  # noqa: E402
import verify_stage1_reported_regressions_ready as ready  # noqa: E402


class TitleNightfallMgbaGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        (ROOT / "tmp").mkdir(exist_ok=True)
        cls.rom = r366.DEFAULT_OUTPUT.read_bytes()
        cls.attributes, cls.palettes = gate.expected_title_payload(cls.rom)

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(
            prefix="title-nightfall-unit-", dir=ROOT / "tmp"
        )
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_report(self, path: Path, *, palettes: bytes | None = None,
                     attributes: bytes | None = None,
                     ffc1: int = 0) -> None:
        palettes = self.palettes if palettes is None else palettes
        attributes = self.attributes if attributes is None else attributes
        lines = [
            "frame=300", "d880=01", f"ffc1={ffc1}", "lcdc=83",
            "scx=8", "scy=8", "base=9800",
            "bgcram=" + (bytes(8) + palettes + bytes(8)).hex().upper(),
        ]
        for row in range(1, 19):
            values = attributes[(row - 1) * 32:row * 32][:21]
            lines.append(
                f"r{row:02d}=" + " ".join(f"{value:02X}" for value in values)
            )
        path.write_text("\n".join(lines) + "\n")

    @staticmethod
    def write_nightfall_image(path: Path) -> None:
        colours = sorted(gate.EXPECTED_RENDERED_COLOURS)
        field = (24, 33, 99)
        image = Image.new("RGB", (160, 144), field)
        for index, colour in enumerate(colours):
            image.putpixel((index, 0), colour)
        image.save(path)

    def analyze(self, name: str) -> dict:
        return gate.analyze_snapshot(
            label=name,
            text_path=self.root / f"{name}.txt",
            png_path=self.root / f"{name}.png",
            expected_attributes=self.attributes,
            expected_palettes=self.palettes,
        )

    def test_reviewed_payload_and_dark_chromatic_raster_pass(self) -> None:
        self.write_report(self.root / "good.txt")
        self.write_nightfall_image(self.root / "good.png")
        result = self.analyze("good")
        self.assertEqual(set(result["attribute_histogram"]),
                         {"1", "2", "3", "4", "5", "6"})
        self.assertEqual(result["dominant_field"], [24, 33, 99])
        self.assertEqual(result["rendered_colours"], 5)

    def test_old_readable_white_grayscale_menu_is_rejected(self) -> None:
        self.write_report(self.root / "white.txt")
        image = Image.new("RGB", (160, 144), (248, 248, 248))
        for x in range(40):
            image.putpixel((x, 40), (0, 0, 0))
        image.save(self.root / "white.png")
        with self.assertRaisesRegex(gate.GateFailure,
                                    "only 2 rendered colours"):
            self.analyze("white")

    def test_stale_cram_is_rejected_even_with_good_pixels(self) -> None:
        stale = bytearray(self.palettes)
        stale[0] ^= 1
        self.write_report(self.root / "cram.txt", palettes=bytes(stale))
        self.write_nightfall_image(self.root / "cram.png")
        with self.assertRaisesRegex(gate.GateFailure,
                                    "BG1..BG6 do not match"):
            self.analyze("cram")

    def test_wrong_chromatic_raster_is_rejected(self) -> None:
        self.write_report(self.root / "pixels.txt")
        self.write_nightfall_image(self.root / "pixels.png")
        image = Image.open(self.root / "pixels.png").convert("RGB")
        image.putpixel((0, 0), (0, 255, 0))
        image.save(self.root / "pixels.png")
        with self.assertRaisesRegex(gate.GateFailure,
                                    "Nightfall colour set changed"):
            self.analyze("pixels")

    def test_stale_attribute_cell_is_rejected(self) -> None:
        stale = bytearray(self.attributes)
        stale[0] = 0
        self.write_report(self.root / "attr.txt", attributes=bytes(stale))
        self.write_nightfall_image(self.root / "attr.png")
        with self.assertRaisesRegex(gate.GateFailure,
                                    "title attributes differ"):
            self.analyze("attr")

    def test_candidate_is_hash_bound(self) -> None:
        self.assertEqual(
            hashlib.sha256(self.rom).hexdigest(),
            r366.EXPECTED_CANDIDATE_SHA256,
        )

    def test_stage1_rollup_reopens_both_rasters_and_reports(self) -> None:
        snapshots = {}
        for label in ("cold", "returned"):
            text_path = self.root / f"title.{label}.txt"
            png_path = self.root / f"title.{label}.png"
            self.write_report(text_path, ffc1=int(label == "returned"))
            self.write_nightfall_image(png_path)
            snapshots[label] = gate.analyze_snapshot(
                label=label,
                text_path=text_path,
                png_path=png_path,
                expected_attributes=self.attributes,
                expected_palettes=self.palettes,
            )
        receipt = {
            "schema": gate.SCHEMA,
            "status": "pass",
            "candidate": str(r366.DEFAULT_OUTPUT.resolve()),
            "candidate_sha256": r366.EXPECTED_CANDIDATE_SHA256,
            "palette_yaml": str(gate.title.PALETTE_YAML.resolve()),
            "palette_yaml_sha256": gate.sha256(
                gate.title.PALETTE_YAML.resolve()
            ),
            "active_scheme": "Nightfall",
            "probe": {
                "status": "ok",
                "message": "cold-and-returned-title-captured",
                "frames": "6000",
                "deferred_wram_frames": "0",
                "transitions": "1:FF>01,2000:01>1C,5000:1B>01",
                "cold_captured": "true",
                "left_title": "true",
                "returned_captured": "true",
            },
            "snapshots": snapshots,
            "checks": {name: True for name in ready.TITLE_NIGHTFALL_CHECKS},
            "tool_identity": {
                "verifier_sha256": ready.sha256(
                    ready.TITLE_NIGHTFALL_VERIFIER
                ),
                "probe_sha256": ready.sha256(ready.TITLE_NIGHTFALL_PROBE),
                "singleflight_sha256": ready.sha256(gate.SINGLEFLIGHT),
            },
            "failures": [],
        }
        receipt_path = self.root / "receipt.json"
        receipt_path.write_text(json.dumps(receipt))
        evidence = ready.validate_title_nightfall_receipt(
            receipt_path,
            r366.DEFAULT_OUTPUT.resolve(),
            r366.EXPECTED_CANDIDATE_SHA256,
        )
        self.assertEqual(evidence["active_scheme"], "Nightfall")

        Image.new("RGB", (160, 144), (248, 248, 248)).save(
            self.root / "title.returned.png"
        )
        with self.assertRaises(ready.NotReady):
            ready.validate_title_nightfall_receipt(
                receipt_path,
                r366.DEFAULT_OUTPUT.resolve(),
                r366.EXPECTED_CANDIDATE_SHA256,
            )


if __name__ == "__main__":
    unittest.main()
