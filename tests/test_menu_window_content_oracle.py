from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import verify_menu_window_order as menu_window  # noqa: E402


class MenuWindowContentOracleTests(unittest.TestCase):
    def test_release_route_leaves_time_for_complete_raster_schedule(self) -> None:
        from verify_release_candidate import build_gates
        gate = next(g for g in build_gates(ROOT/'missing-test-rom.gb', ROOT/'tmp')
                    if g.name == 'menu_window_publish_order')
        def option(name):
            return int(gate.command[gate.command.index(name)+1])
        fixture, _, _ = menu_window.load_content_fixture()
        # Allow entry latency as well as every required visible-age sample.
        self.assertGreaterEqual(option('--close-frame')-1200,
                                max(fixture['raster']['sample_visible_ages'])+20)
        self.assertGreaterEqual(option('--frames')-option('--close-frame'),60)
        self.assertEqual(option('--force-map-alias-frame'),1250)

    def setUp(self) -> None:
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(
            prefix="menu-window-content-", dir=ROOT / "tmp"
        )
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def trace(self, path: Path, fixture: dict) -> str:
        return ";".join(
            f"f{1202 + age}:a{age}:p{path}"
            for age in fixture["raster"]["sample_visible_ages"]
        )

    @staticmethod
    def invariant_payload(image: Image.Image, fixture: dict) -> bytes:
        return b"".join(
            image.crop(tuple(region)).tobytes()
            for region in fixture["raster"]["regions"]
        )

    def test_reviewed_fixture_is_independent_and_covers_native_labels(self) -> None:
        fixture, expected, mask = menu_window.load_content_fixture()
        self.assertEqual(len(expected), 120)
        self.assertEqual(len(mask), 120)
        self.assertGreaterEqual(sum(mask), 80)
        self.assertEqual(expected[12:19], bytes.fromhex("E0 D5 E1 E3 E4 E5 E6"))
        self.assertEqual(expected[100:110], bytes.fromhex(
            "C0 C1 C2 C3 C4 D0 D1 D2 D3 D4"
        ))
        self.assertEqual(fixture["schema"], menu_window.CONTENT_FIXTURE_SCHEMA)

    def test_blank_white_menu_fails_even_when_every_sample_matches_itself(self) -> None:
        fixture, _, _ = menu_window.load_content_fixture()
        white = self.root / "white.png"
        Image.new("RGB", (160, 144), (255, 255, 255)).save(white)
        receipt = menu_window.content_raster_receipt(
            self.trace(white, fixture), fixture
        )
        self.assertFalse(receipt["passed"])
        self.assertEqual(receipt["checked_frames"], 7)
        self.assertEqual(receipt["bad_frames"], 7)
        self.assertEqual(
            receipt["first_bad"]["reason"],
            "rendered fixed HUD pixels differ",
        )

    def test_every_scheduled_rendered_sample_is_checked(self) -> None:
        fixture, _, _ = menu_window.load_content_fixture()
        fixture = copy.deepcopy(fixture)
        image = Image.new("RGB", (160, 144), (0, 0, 0))
        pixels = image.load()
        for y in range(96, 144):
            for x in range(160):
                if (x + y) % 5 == 0:
                    pixels[x, y] = (255, 255, 255)
        good = self.root / "good.png"
        image.save(good)
        fixture["raster"]["expected_rgb_sha256"] = hashlib.sha256(
            self.invariant_payload(image, fixture)
        ).hexdigest()
        receipt = menu_window.content_raster_receipt(
            self.trace(good, fixture), fixture
        )
        self.assertTrue(receipt["passed"])
        self.assertEqual(receipt["checked_frames"], 7)

        short_trace = ";".join(
            self.trace(good, fixture).split(";")[:-1]
        )
        short = menu_window.content_raster_receipt(short_trace, fixture)
        self.assertFalse(short["passed"])
        self.assertEqual(
            short["first_bad"]["reason"], "raster sample schedule mismatch"
        )


if __name__ == "__main__":
    unittest.main()
