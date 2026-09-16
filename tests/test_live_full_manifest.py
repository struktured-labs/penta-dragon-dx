"""Read-only pre-stream evidence controls; synthetic manifests are never saved."""
import copy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))
import verify_live_regression as live
import verify_release_candidate as release
import runtime_tools


class LiveFullManifestTests(unittest.TestCase):
    def test_current_r534_contract_includes_all_90_gates_without_emulator(self):
        with patch.object(live.subprocess, "run", side_effect=AssertionError("unexpected subprocess")):
            gates, errors = live.profile_gates(ROOT / "tmp/stage4-cache-key-r534/candidate.gb")
        self.assertEqual(errors, [])
        self.assertEqual(len(gates), 90)
        for name in ("gameplay_movement_stress", "low_health_scene0b_publication",
                     "pocket_stage1_visual_incident", "stage1_current_pickup_state",
                     "stage1_current_pickup_host_palettes", "gameover_restart",
                     "gameover_spike_restart", "gameover_saved_spike_restart"):
            self.assertIn(name, gates)

    def test_inventory_still_rejects_future_omissions(self):
        with patch.object(live, "registered_gate_names", return_value={"unlisted-gate"}):
            _, errors = live.profile_gates(Path("unused"))
        self.assertTrue(any("omitted" in error for error in errors))

    def test_read_only_option_cannot_launch_or_resume(self):
        for extra in (["--resume"], ["--output", "tmp/unused"], ["--list"], ["--check-contract"]):
            with patch.object(sys, "argv", ["live", "--verify-manifest", "unused.json", *extra]), \
                 patch.object(live.subprocess, "run", side_effect=AssertionError("unexpected emulator")), \
                 redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    live.main()
                self.assertEqual(error.exception.code, 2)

    def fixture(self):
        rom = b"unit-only ROM"
        import hashlib
        md5 = hashlib.md5(rom).hexdigest()
        runtime = {"identity": "unit-only"}
        manifest = {"status": "emulator-pass", "scope": "full", "failures": 0,
                    "rom_md5": md5, "rom_size": len(rom), "source_rom_md5_after": md5,
                    "tested_rom_md5_after": md5, "rom_hashes_intact": True,
                    "source_inputs_intact": True, "source_fingerprint": "snapshot",
                    "source_fingerprint_after": "snapshot", "source_input_count": 1,
                    "runtime_tools_intact": True, "runtime_tools": runtime, "runtime_tools_after": runtime,
                    "source_rom": "source.gb", "tested_rom": "tested.gb", "selected_gates": ["a", "b"],
                    "results": [{"name": name, "status": "passed", "returncode": 0} for name in ("a", "b")]}
        return manifest, rom, runtime

    def check(self, manifest, rom, runtime, damaged_path=None):
        def reader(path):
            if str(path) == damaged_path:
                return b"different ROM"
            return json.dumps(manifest).encode() if path.name == "unit.json" else rom
        with patch.object(Path, "read_bytes", side_effect=None, autospec=True) as read, \
             patch.object(live, "source_snapshot", return_value=("snapshot", [{}])), \
             patch.object(runtime_tools, "emulator_runtime_snapshot", return_value=runtime), \
             patch.object(release, "build_gates", return_value=[SimpleNamespace(name=n) for n in ("a", "b")]), \
             patch.object(live.subprocess, "run", side_effect=AssertionError("unexpected emulator")), \
             redirect_stdout(io.StringIO()):
            read.side_effect = reader
            return live.verify_full_manifest(Path("unit.json"), Path("candidate.gb"), ("a", "b"))

    def test_complete_current_full_matrix_is_accepted_without_writes(self):
        manifest, rom, runtime = self.fixture()
        with patch.object(Path, "write_text", side_effect=AssertionError("unexpected evidence write")), \
             patch.object(Path, "write_bytes", side_effect=AssertionError("unexpected evidence write")):
            self.assertEqual(self.check(manifest, rom, runtime), 0)

    def test_stale_partial_reordered_mutated_runtime_or_policy_is_rejected(self):
        manifest, rom, runtime = self.fixture()
        mutations = (
            lambda m: m.update(scope="selected", status="selected-pass"),
            lambda m: m.update(source_fingerprint="stale"),
            lambda m: m.update(runtime_tools={}),
            lambda m: m.update(runtime_tools_after={}),
            lambda m: m.update(rom_hashes_intact=1),
            lambda m: m["results"].pop(),
            lambda m: (m["results"].reverse(), m["selected_gates"].reverse()),
            lambda m: m["results"][0].update(returncode=False),
            lambda m: m["results"][1].update(status="failed"),
        )
        for index, mutate in enumerate(mutations):
            bad = copy.deepcopy(manifest)
            mutate(bad)
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.check(bad, rom, runtime)
        for path in ("source.gb", "tested.gb"):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "bytes differ"):
                self.check(manifest, rom, runtime, path)


if __name__ == "__main__":
    unittest.main()
