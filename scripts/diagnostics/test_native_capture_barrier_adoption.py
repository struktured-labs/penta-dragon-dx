#!/usr/bin/env python3
"""#43 adoption controls: restored native captures always use the barrier.

These tests never launch an emulator (subprocess is mocked).
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import runpy
import subprocess
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts/diagnostics/run_secret_entry_probe.py"
STATE = "tmp/secret-alias-chunk-lowhealth-return-01/frame-0960.ss0"
ROM = "tmp/secret-alias-chunk-trial-01/candidate.gb"
TAP = ROOT / "scripts/diagnostics/native_av_tap.c"  # any existing file; never loaded
CAPTURE_RUNNERS = (
    "scripts/diagnostics/prepare_native_replay.py",
    "scripts/diagnostics/run_secret_entry_probe.py",
    "scripts/diagnostics/replay_boss_menu_roundtrips.py",
    "scripts/probes/verify_phantom_d887.py",
)


class SecretRunnerBarrier(unittest.TestCase):
    def invoke(self, state, extra):
        if not (ROOT / ROM).exists() or (state != "cold" and not (ROOT / state).exists()):
            self.skipTest("local fixture unavailable")
        name = "barrier-adoption-" + uuid.uuid4().hex
        env = {"ENTRY_ROM": str(ROOT / ROM), "ENTRY_FRAMES": "1",
               "ENTRY_NATIVE_TAP": str(TAP), **extra}
        captured = []
        with patch.dict(os.environ, env, clear=True), \
             patch.object(sys, "argv", [str(RUNNER), state, name]), \
             patch("subprocess.run", return_value=subprocess.CompletedProcess([], 75)) as run, \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as stop:
                runpy.run_path(str(RUNNER), run_name="__main__")
            captured = run.call_args_list
        self.assertEqual(stop.exception.code, 75)
        self.assertEqual(len(captured), 1)
        receipt = json.loads((ROOT / "tmp" / name / "receipt.json").read_text())
        return name, captured[0].kwargs["env"], captured[0].args[0], receipt

    def tearDown(self):
        for capture in Path("/mnt/data/tmp").glob("penta-barrier-adoption-*-av") \
                if Path("/mnt/data/tmp").is_dir() else ():
            if not any(capture.iterdir()):
                capture.rmdir()
        for capture in (ROOT / "tmp").glob("penta-barrier-adoption-*-av"):
            if not any(capture.iterdir()):
                capture.rmdir()

    def test_restored_native_capture_defaults_to_barrier(self):
        name, env, command, receipt = self.invoke(STATE, {})
        self.assertEqual(Path(env["ENTRY_NATIVE_START_GATE"]),
                         (ROOT / "tmp" / name / "native-start-gate").resolve())
        self.assertFalse(Path(env["ENTRY_NATIVE_START_GATE"]).exists(),
                         "marker must not pre-exist (tap exits 74)")
        self.assertIn("-t", command)
        self.assertEqual(receipt["native_start_gate"], "barrier")
        self.assertEqual(env["ENTRY_AUDIO_ENABLED"], "1")

    def test_ungated_capture_only_as_labeled_negative_control(self):
        _, env, _, receipt = self.invoke(STATE, {"ENTRY_NATIVE_UNGATED_NEGATIVE_CONTROL": "1"})
        self.assertNotIn("ENTRY_NATIVE_START_GATE", env)
        self.assertEqual(receipt["native_start_gate"], "ungated-negative-control")

    def test_cold_capture_has_no_restore_epoch_to_gate(self):
        _, env, command, receipt = self.invoke("cold", {})
        self.assertNotIn("ENTRY_NATIVE_START_GATE", env)
        self.assertNotIn("-t", command)
        self.assertIsNone(receipt["native_start_gate"])


class StaticAdoption(unittest.TestCase):
    def test_every_restored_native_runner_sets_the_gate(self):
        for rel in CAPTURE_RUNNERS:
            source = (ROOT / rel).read_text()
            with self.subTest(runner=rel):
                self.assertIn("PENTA_NATIVE_AV_PREFIX", source)
                restores = re.search(r"['\"]-t['\"]", source) is not None
                if restores:
                    self.assertIn("ENTRY_NATIVE_START_GATE", source)

    def test_no_other_runner_enables_native_capture(self):
        hits = set()
        for directory in ("scripts/diagnostics", "scripts/probes", "scripts"):
            for path in (ROOT / directory).glob("*.py"):
                if path.resolve() == Path(__file__).resolve():
                    continue
                text = path.read_text(errors="ignore")
                if re.search(r"PENTA_NATIVE_AV_PREFIX\s*=", text):
                    hits.add(str(path.relative_to(ROOT)))
        self.assertLessEqual(hits, set(CAPTURE_RUNNERS), hits - set(CAPTURE_RUNNERS))

    def test_phantom_native_capture_uses_explicit_audio(self):
        sys.path.insert(0, str(ROOT / "scripts/probes"))
        import verify_phantom_d887 as phantom
        self.assertEqual(phantom.NATIVE_AUDIO_OPTIONS,
                         ("mute=0", "volume=256", "fastForwardMute=-1", "fastForwardVolume=256"))
        source = (ROOT / "scripts/probes/verify_phantom_d887.py").read_text()
        self.assertIn("*audio_options", source)


if __name__ == "__main__":
    unittest.main()
