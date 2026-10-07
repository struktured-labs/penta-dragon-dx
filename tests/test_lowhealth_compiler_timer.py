"""#59 negative controls for the narrow interrupt-latency gate."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
from check_lowhealth_compiler_timer import assess,TIMER_PERIOD,MAX_GAP


class CompilerTimer(unittest.TestCase):
    def rows(self):
        return [dict(kind='timer',cycle=str(i*TIMER_PERIOD),frame=str(i*899//1341),
                     bank='1E',svbk='01',scene='0B',canonical='03',stage='01') for i in range(1342)]

    def test_bounded_trace(self):self.assertTrue(assess(self.rows())['passed'])

    def test_late_gap_rejected(self):
        rows=self.rows()
        for r in rows[30:]:r['cycle']=str(int(r['cycle'])+MAX_GAP-TIMER_PERIOD+1)
        with self.assertRaises(ValueError):assess(rows)

    def test_wrong_bank_or_scene_rejected(self):
        for field,value in [('svbk','03'),('scene','03'),('canonical','0C'),('stage','00')]:
            rows=self.rows();rows[30][field]=value
            with self.assertRaises(ValueError):assess(rows)

    def test_missing_work_or_truncation_rejected(self):
        rows=self.rows()
        with self.assertRaises(ValueError):assess(rows[:1299])
        with self.assertRaises(ValueError):assess(rows[3:])
        with self.assertRaises(ValueError):assess(rows[:-1])
        for r in rows:r['bank']='01'
        with self.assertRaises(ValueError):assess(rows)


if __name__=='__main__':unittest.main()
