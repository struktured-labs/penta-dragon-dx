import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "runtime_tools", ROOT / "scripts/diagnostics/runtime_tools.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class RuntimeToolsTests(unittest.TestCase):
    def test_cgb_preflight_rejects_bad_library_in_either_emulator(self):
        for mode in ('qt', 'headless'):
            with self.subTest(mode=mode):
                snapshot = {name: {'libraries': []} for name in ('qt', 'headless')}
                snapshot[mode]['libraries'] = [{
                    'path': '/renamed/libmgba.so',
                    'sha256': runtime.BROKEN_CGB_LATCH_LIBRARY,
                }]
                with self.assertRaisesRegex(RuntimeError, 'known-broken CGB latch'):
                    runtime.reject_known_broken_cgb_runtime(snapshot)

    def test_cgb_preflight_accepts_corrected_library_without_claiming_pass(self):
        snapshot = {name: {'libraries': [{
            'path': '/isolated/libmgba.so',
            'sha256': '20fa5ddaf77abed9cf55972616242a232181a04fb1d52bf3e38e58e7b809b4cf',
        }]} for name in ('qt', 'headless')}
        self.assertIsNone(runtime.reject_known_broken_cgb_runtime(snapshot))

    def test_library_resolution_and_content_identity(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as directory:
            library = Path(directory) / "libtest.so"
            library.write_bytes(b"old")
            listing = f"libtest.so => {library} (0x1234)\n{library} (0x5678)"
            self.assertEqual(runtime.library_paths(listing), [library.resolve()])
            old = runtime.identity(library)
            library.write_bytes(b"new")
            self.assertNotEqual(old, runtime.identity(library))

    def test_missing_library_is_fatal(self):
        with self.assertRaises(RuntimeError):
            runtime.library_paths("libmgba.so.0.11 => not found")

    def test_runtime_comparison_accepts_equivalent_checkout_symlinks(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as directory:
            scratch = Path(directory)
            physical = scratch / "physical"
            alias = scratch / "alias"
            physical.mkdir()
            alias.symlink_to(physical, target_is_directory=True)
            recorded = {
                "LD_LIBRARY_PATH": str(alias),
                "LD_PRELOAD": "",
                "qt": {"binary": {"sha256": "same"}},
            }
            observed = {
                "LD_LIBRARY_PATH": str(physical),
                "LD_PRELOAD": "",
                "qt": {"binary": {"sha256": "same"}},
            }
            self.assertTrue(runtime.runtime_snapshots_match(recorded, observed))

            observed["LD_PRELOAD"] = "/different/preload.so"
            self.assertFalse(runtime.runtime_snapshots_match(recorded, observed))

    def test_runtime_comparison_rejects_distinct_loader_directories(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as directory:
            scratch = Path(directory)
            first = scratch / "first"
            second = scratch / "second"
            first.mkdir()
            second.mkdir()
            recorded = {"LD_LIBRARY_PATH": str(first)}
            observed = {"LD_LIBRARY_PATH": str(second)}
            self.assertFalse(runtime.runtime_snapshots_match(recorded, observed))
