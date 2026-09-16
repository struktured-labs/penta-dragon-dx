"""Exercise probe completion with ordinary child processes, never an emulator."""
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))
from verify_stage1_spike_palettes import run_probe_process


class ProbeCompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)

    def run_child(self, code, timeout=2):
        with (self.path / "child.log").open("w") as log:
            return run_probe_process(
                [sys.executable, "-c", code], cwd=self.path, env=os.environ.copy(),
                stream=log, timeout=timeout, done_path=self.path / "probe.done",
                report_path=self.path / "probe.txt",
                screenshot_path=self.path / "probe.png",
            )

    def test_complete_probe_reaped_without_waiting_for_deadline(self):
        start = time.monotonic()
        child, timed_out, cleanup = self.run_child(
            "from pathlib import Path; from PIL import Image; import time; "
            "Path('probe.txt').write_text('probe_finished=1\\n'); "
            "Image.new('RGB', (160, 144)).save('probe.png'); "
            "Path('probe.done').write_text('probe_finished=1\\n'); time.sleep(30)",
            timeout=10,
        )
        self.assertTrue(cleanup)
        self.assertFalse(timed_out)
        self.assertLess(time.monotonic() - start, 5)
        self.assertIsNotNone(child.returncode)

    def test_stale_sentinel_cannot_complete_new_run(self):
        (self.path / "probe.done").write_text("probe_finished=1\n")
        child, timed_out, cleanup = self.run_child("import time; time.sleep(30)", .2)
        self.assertTrue(timed_out)
        self.assertFalse(cleanup)
        self.assertEqual(child.returncode, 124)

    def test_marker_without_terminal_artifacts_is_incomplete(self):
        _, timed_out, cleanup = self.run_child(
            "from pathlib import Path; import time; "
            "Path('probe.done').write_text('probe_finished=1\\n'); time.sleep(30)", .3,
        )
        self.assertTrue(timed_out)
        self.assertFalse(cleanup)

    def test_normal_failure_is_preserved(self):
        child, timed_out, cleanup = self.run_child("raise SystemExit(75)")
        self.assertEqual(child.returncode, 75)
        self.assertFalse(timed_out)
        self.assertFalse(cleanup)


if __name__ == "__main__":
    unittest.main()
