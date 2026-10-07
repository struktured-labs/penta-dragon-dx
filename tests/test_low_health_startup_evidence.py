"""#67 retained native-output controls; no emulator launch or aligned comparison."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "epoch", ROOT / "scripts/diagnostics/verify_native_capture_epoch.py")
EPOCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EPOCH)


class LowHealthStartupEvidence(unittest.TestCase):
    def test_default_runner_preserves_complete_native_outputs(self):
        path = self.directory("lowhealth-default-native-01")
        receipt = json.loads((path / "receipt.json").read_text())
        self.assertTrue(receipt["passed"])
        self.assertEqual(len(receipt["checks"]), 3)
        for index in (1, 2):
            child = json.loads((path / f"replay-{index}/receipt.json").read_text())
            build = child["native_replay"]
            self.assertTrue(build["bindings"])
            self.assertEqual(child["native_capture"]["restored_replay_epoch"]["status"], "PASS")

    def directory(self, name):
        path = ROOT / "tmp" / name
        if not (path / "receipt.json").is_file():
            self.skipTest("local native replay evidence unavailable")
        return path

    def test_barrier_and_explicit_audio_preserve_all_primary_outputs(self):
        first = self.directory("lowhealth-explicit-audio-01")
        second = self.directory("lowhealth-explicit-audio-delay-01")
        receipts = [json.loads((path / "receipt.json").read_text())
                    for path in (first, second)]
        for receipt in receipts:
            self.assertTrue(receipt["passed"])
            self.assertEqual(receipt["audio_options"], [
                "mute=0", "volume=256", "fastForwardMute=-1", "fastForwardVolume=256"])
        for key in ("rom_sha256", "state_sha256"):
            self.assertEqual(receipts[0][key], receipts[1][key])
        for path in (first, second):
            self.assertEqual(EPOCH.verify(path)["status"], "PASS")
        for suffix in ("s16le", "video", "states", "timeline.tsv"):
            with self.subTest(suffix=suffix):
                # Complete bytes: no trim, shift, normalization, or field mask.
                self.assertTrue((first / ("native." + suffix)).read_bytes()
                                == (second / ("native." + suffix)).read_bytes())

    def test_ungated_delay_is_rejected_despite_visual_gate_pass(self):
        path = self.directory("lowhealth-explicit-audio-ungated-01")
        self.assertTrue(json.loads((path / "receipt.json").read_text())["passed"])
        epoch = EPOCH.verify(path)
        self.assertEqual(epoch["status"], "FAIL")
        self.assertEqual(epoch["events"][0]["pcm_samples"], 512)

    def test_inherited_audio_failure_is_retained(self):
        first = self.directory("lowhealth-startup-barrier-01")
        second = self.directory("lowhealth-startup-barrier-delay-01")
        self.assertFalse((first / "native.s16le").read_bytes()
                         == (second / "native.s16le").read_bytes())
        self.assertTrue((first / "native.video").read_bytes()
                        == (second / "native.video").read_bytes())


if __name__ == "__main__":
    unittest.main()
