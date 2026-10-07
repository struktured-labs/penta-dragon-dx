"""#59 reject invalid menu-input schedules before any emulator/file activity."""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]


class MenuCloseSchedule(unittest.TestCase):
    def test_invalid_pulses_fail_before_loading_inputs(self):
        for frame in (0,-1,1795,1800,999999):
            result=subprocess.run([
                sys.executable,str(ROOT/'scripts/diagnostics/run_shalamar_transition.py'),
                '--rom','does-not-exist.gb','--state','does-not-exist.ss0',
                '--output',str(ROOT/'tmp/must-not-be-created-by-menu-unit'),
                '--defeat-frame','1800','--frames','4200',
                '--close-menu-frame',str(frame)],capture_output=True,text=True)
            self.assertEqual(result.returncode,2,result.stderr)
            self.assertIn('menu-close pulse must finish before defeat stimulus',result.stderr)
            self.assertNotIn('Traceback',result.stderr)


if __name__=='__main__':unittest.main()
