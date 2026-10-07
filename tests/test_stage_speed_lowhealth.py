"""Issue #59: low-health speed checks retain native scene identity."""
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / 'scripts/diagnostics/verify_stage_speed_matrix.py'
SPEC = importlib.util.spec_from_file_location('speed_lowhealth', PATH)
speed = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(speed)


class LowHealthIdentity(unittest.TestCase):
    def test_normal_stages_keep_original_expectation(self):
        for target in range(7):
            result = dict(health_assistance=255, expected_scene=target+2,
                          final_scene=target+2)
            self.assertTrue(speed.health_scene_ok(result, target, 255))
            result['final_scene'] = 11
            self.assertFalse(speed.health_scene_ok(result, target, 255))

    def test_lowhealth_requires_raw_and_canonical_identity(self):
        for target in range(7):
            result = dict(health_assistance=109, expected_scene=11,
                          final_scene=11, canonical_scene=target+2,
                          selected_stage=target)
            self.assertTrue(speed.health_scene_ok(result, target, 109))
            for field in result:
                bad = dict(result)
                bad[field] += 1
                self.assertFalse(speed.health_scene_ok(bad, target, 109), field)
                del bad[field]
                self.assertFalse(speed.health_scene_ok(bad, target, 109), field)


if __name__ == '__main__':
    unittest.main()
