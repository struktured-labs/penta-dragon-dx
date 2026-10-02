from pathlib import Path
import sys
import unittest
import tempfile
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/diagnostics"))
from verify_stage1_captured_menu import summarize, room01_lut, operator_retarget, incident_raster


class CapturedMenuTests(unittest.TestCase):
    def test_clean_memory_cannot_hide_one_rendered_splatter_frame(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=root / "tmp", prefix="menu-raster-test-") as temp:
            out = Path(temp)
            rows = self.rows()
            for row in rows:
                row.update(scx="0C", scy="08")
                frame = int(row["frame"])
                if 60 <= frame < 240:
                    Image.new("RGB", (160,144), (255,255,255)).save(out / f"frame-{frame:04d}.png")
            expected = [(255,255,255)] * (32 * 40)
            self.assertTrue(incident_raster(rows, out, expected)["passed"])
            bad = Image.new("RGB", (160,144), (255,255,255))
            bad.putpixel((2,3), (255,0,0))
            bad.save(out / "frame-0066.png")
            result = incident_raster(rows, out, expected)
            self.assertFalse(result["passed"])
            self.assertEqual(result["bad_frames"], [{"frame":66, "pixels":1}])
            self.assertTrue(all(summarize(rows)["checks"].values()))

    def test_unknown_operator_state_cannot_become_a_clean_baseline(self):
        with self.assertRaisesRegex(ValueError, "SHA differs"):
            operator_retarget(b"unknown", bytes(0x80000))

    def test_short_close_flash_is_reported_separately(self):
        rows = self.rows()
        rows[67]["mismatches"] = "47"
        result = summarize(rows)
        self.assertEqual(result["close_transition_bad_frames"], 1)
        self.assertEqual(result["stationary_bad_frames"], 0)
        self.assertFalse(result["checks"]["immediate closed-menu background has exact canonical attributes"])

    def test_room01_wall_companions_are_not_reported_as_corruption(self):
        rom = bytearray(0x80000)
        for tile in (0x24, 0x27, 0x30, 0x33):
            rom[20 * 0x4000 + 0x600 + tile] = 6
        lut = room01_lut(bytes(rom))
        self.assertEqual([i for i,v in enumerate(lut) if v], [0x24,0x27,0x30,0x33])
        self.assertEqual(set(lut), {0,6})
        rom[20 * 0x4000 + 0x600 + 0x27] = 1
        with self.assertRaises(ValueError):
            room01_lut(bytes(rom))

    def rows(self):
        return [{"frame": str(f), "menu": "01" if f < 66 else "00",
                 "lcdc": "E3" if f < 66 else "C3", "scene": "02", "room": "01",
                 "keys": "02" if 60 <= f < 66 else ("40" if 240 <= f < 264 else "00"),
                 "mismatches": "0"} for f in range(1, 361)]

    def test_clean_stationary_close_passes(self):
        self.assertTrue(all(summarize(self.rows())["checks"].values()))

    def test_movement_recovery_cannot_hide_stationary_corruption(self):
        rows = self.rows()
        for row in rows:
            if 90 <= int(row["frame"]) < 240:
                row["mismatches"] = "12"
        result = summarize(rows)
        self.assertEqual(result["stationary_bad_frames"], 150)
        self.assertEqual(result["recovery_bad_frames"], 0)
        self.assertFalse(result["checks"]["stationary background has exact canonical attributes"])

    def test_missing_frames_movement_and_unclosed_menu_fail(self):
        rows = self.rows()
        del rows[95]
        self.assertFalse(summarize(rows)["checks"]["all 360 consecutive frames retained"])
        for key, value, check in (("keys", "40", "no input during stationary close interval"),
                                  ("menu", "01", "menu ownership and Window are released")):
            rows = self.rows()
            rows[100][key] = value
            self.assertFalse(summarize(rows)["checks"][check])


if __name__ == "__main__":
    unittest.main()
