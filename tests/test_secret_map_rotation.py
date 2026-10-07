"""Negative controls for #54's replay evidence evaluator."""
import importlib.util
from pathlib import Path
import unittest

PATH=Path(__file__).resolve().parents[1]/'scripts/diagnostics/verify_secret_map_rotation.py'
spec=importlib.util.spec_from_file_location('secret_rotation',PATH)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SecretRotationTest(unittest.TestCase):
    def trace(self, count=4800):
        return [[str(i),'09','07','01','01','03','0','0','255',str(i),'1400','0','0','0','0']
                for i in range(1,count+1)]

    def test_complete_route_and_positions(self):
        result=module.assess(self.trace(),[])
        self.assertTrue(result['complete'])
        self.assertEqual(result['secret_frames'],4800)
        self.assertEqual(result['distinct_positions'],4800)
        self.assertEqual(result['rotation_count'],0)

    def test_truncated_route_rejected(self):
        self.assertFalse(module.assess(self.trace(4799),[])['complete'])

    def test_broken_map_write_detected(self):
        result=module.assess(self.trace(),[dict(address='C3E5',before='01',after='80')])
        self.assertEqual(result['map_rotation_changes'],1)

    def test_noop_is_not_broken_control_reproduction(self):
        result=module.assess(self.trace(),[dict(address='C3E5',before='00',after='00')])
        self.assertEqual(result['map_rotation_changes'],0)
        self.assertEqual(result['rotation_count'],1)

    def test_other_address_not_claimed_map_damage(self):
        result=module.assess(self.trace(),[dict(address='0061',before='01',after='80')])
        self.assertEqual(result['map_rotation_changes'],0)

    def test_other_stage_not_secret_coverage(self):
        rows=self.trace()
        for row in rows: row[2]='01'
        self.assertEqual(module.assess(rows,[])['secret_frames'],0)


if __name__=='__main__':
    unittest.main()
