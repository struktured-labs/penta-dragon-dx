import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/diagnostics"))
from summarize_low_health_floor_trace import summarize


class FloorTraceTest(unittest.TestCase):
    def test_exact_floor_and_bounds(self):
        rows = [dict(stimulus_phase="recovered", frame=str(i),
                     tile_bytes="01020426", attr_bytes=a)
                for i, a in enumerate(("00000006", "05060006", "00000006"), 10)]
        result = summarize(rows)["recovered"]
        self.assertEqual(result["bad_frames"], 1)
        self.assertEqual(result["maximum_bad_cells"], 2)
        self.assertEqual(result["first_bad_frame"], 11)
        self.assertEqual(result["last_bad_frame"], 11)
        rows[0]["attr_bytes"] = "00"
        with self.assertRaises(ValueError):
            summarize(rows)
