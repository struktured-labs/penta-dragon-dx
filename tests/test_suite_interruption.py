"""Issue #12: supervisor exceptions clean up only the owned matrix."""
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))
import run_deterministic_suite as runner


class SuiteInterruptionTests(unittest.TestCase):
    def test_interrupt_or_monitor_exception_cleans_exact_owner(self):
        for error in (KeyboardInterrupt(), RuntimeError("monitor failed")):
            with self.subTest(error=type(error).__name__):
                process = MagicMock(pid=12345)
                process.poll.return_value = None
                with patch.object(Path, "open", return_value=io.StringIO()), \
                     patch.object(runner.secrets, "token_hex", return_value="unit-owner"), \
                     patch.object(runner.subprocess, "Popen", return_value=process), \
                     patch.object(runner, "token_process_groups", return_value={12345}), \
                     patch.object(runner, "foreign_mgba_processes", side_effect=error), \
                     patch.object(runner, "stop_matrix_and_owned") as stop, \
                     patch.object(runner, "cleanup_owner_registry") as cleanup:
                    with self.assertRaises(type(error)):
                        runner.run_matrix_guarded(["never-launched"], ROOT / "tmp/unit-log")
                    stop.assert_called_once_with(process, "unit-owner")
                    self.assertEqual(cleanup.call_count, 2)
                    cleanup.assert_called_with("unit-owner")

    def test_interruption_during_initial_owner_discovery_also_cleans(self):
        process = MagicMock(pid=12345)
        with patch.object(Path, "open", return_value=io.StringIO()), \
             patch.object(runner.secrets, "token_hex", return_value="unit-owner"), \
             patch.object(runner.subprocess, "Popen", return_value=process), \
             patch.object(runner, "token_process_groups", side_effect=KeyboardInterrupt), \
             patch.object(runner, "stop_matrix_and_owned") as stop, \
             patch.object(runner, "cleanup_owner_registry"):
            with self.assertRaises(KeyboardInterrupt):
                runner.run_matrix_guarded(["never-launched"], ROOT / "tmp/unit-log")
            stop.assert_called_once_with(process, "unit-owner")
