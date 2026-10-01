import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
from replay_boss_menu_roundtrips import native_capture_failures


class BossNativeCaptureGate(unittest.TestCase):
    def test_complete_valid_epoch(self):
        self.assertEqual(native_capture_failures(dict(
            restored_replay_epoch={'status':'PASS'}, metadata={'frames':1080})),[])

    def test_pre_restore_capture_rejected_despite_complete_files(self):
        self.assertTrue(native_capture_failures(dict(status='COMPLETE_CAPTURE_FILES',
            restored_replay_epoch={'status':'FAIL'},metadata={'frames':1080})))

    def test_missing_and_wrong_frame_counts_rejected(self):
        self.assertEqual(len(native_capture_failures({})),2)
        for count in (1079,1081):
            self.assertTrue(native_capture_failures(dict(
                restored_replay_epoch={'status':'PASS'},metadata={'frames':count})))


if __name__=='__main__': unittest.main()
