"""Fail-closed source-profile and original-build filesystem evidence controls."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts/diagnostics"), str(ROOT / "scripts")]
import r120_historical_profile as profile
import rebuild_r534_from_original as original


class OriginalRebuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        factory = ROOT / "tmp/r120-production-audit-current490/candidate.gb"
        if not factory.is_file():
            raise unittest.SkipTest("exact factory fixture is unavailable")
        cls.factory = factory.read_bytes()
        cls.baseline = (ROOT / "tmp/source-integration-r120/candidate.gb").read_bytes()

    def test_historical_profile_is_exact_and_has_no_artifact_reads(self):
        with patch.object(Path, "read_bytes", side_effect=AssertionError("hidden artifact read")):
            result, receipt = profile.build(self.factory)
            again, second = profile.build(self.factory)
        self.assertEqual((result, receipt), (again, second))
        self.assertEqual(result, self.baseline)
        self.assertEqual(receipt["changed_bytes"], 301)
        self.assertFalse(receipt["retained_roms_read"])
        self.assertFalse(receipt["fresh_live_qualification"])
        self.assertFalse(receipt["promotable"])

    def test_profile_rejects_wrong_factory_and_missing_or_changed_fragments(self):
        with self.assertRaisesRegex(ValueError, "exact freshly generated factory"):
            profile.build(self.factory[:-1])
        first = profile.FRAGMENTS[0]
        for fragments, error in (
            (profile.FRAGMENTS[:-1], "did not reproduce exact r120"),
            ((first, first) + profile.FRAGMENTS[1:], "overlapping fragment"),
            ((first[:2] + ("00000000", first[3]),) + profile.FRAGMENTS[1:], "modern preimage differs"),
            ((first[:3] + ("00",),) + profile.FRAGMENTS[1:], "fragment width changed"),
        ):
            with self.subTest(error=error), patch.object(profile, "FRAGMENTS", fragments):
                with self.assertRaisesRegex(ValueError, error):
                    profile.build(self.factory)

    def test_file_access_trace_accepts_original_and_own_generated_files(self):
        trace = ('123 openat(AT_FDCWD, "rom/Penta Dragon (J).gb", O_RDONLY|O_CLOEXEC) = 3\n'
                 '124 openat(AT_FDCWD, "tmp/source-audit-unit/work/production.gb", O_RDWR) = 3\n')
        receipt = original.audit_factory_access(trace, ROOT / "tmp/source-audit-unit")
        self.assertEqual(receipt["open_calls_checked"], 2)
        self.assertEqual(receipt["retained_scratch_artifact_accesses"], 0)
        self.assertIn("rom/Penta Dragon (J).gb", receipt["repository_inputs"])

    def test_file_access_trace_rejects_retained_paths_even_on_failed_open(self):
        for path in ("tmp/source-integration-r120/candidate.gb",
                     "rom/versions/unqualified.gbc", "tmp/unknown.txt",
                     "src/penta_dragon_dx/__pycache__/display_patcher.cpython-312.pyc"):
            trace = f'123 openat(AT_FDCWD, "{path}", O_RDONLY) = -1 ENOENT\n'
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, "retained scratch|undeclared ROM|cached repository bytecode"):
                    original.audit_factory_access(trace, ROOT / "tmp/source-audit-unit")

    def test_file_access_trace_rejects_ambiguous_or_empty_evidence(self):
        for trace in ("", '123 chdir("/elsewhere") = 0\n', '123 fchdir(3) = 0\n',
                      '123 openat(3, "candidate.gb", O_RDONLY) = 4\n',
                      '123 openat(AT_FDCWD, "x", O_RDONLY <unfinished ...>\n',
                      '123 openat2(AT_FDCWD, "x", {}, 0) = 3\n',
                      '123 openat(AT_FDCWD, NULL, O_RDONLY) = -1\n'):
            with self.subTest(trace=trace), self.assertRaises(ValueError):
                original.audit_factory_access(trace, ROOT / "tmp/source-audit-unit")

    def test_original_build_requires_fresh_repository_scratch_directory(self):
        for output in (ROOT, ROOT / "tmp", ROOT / "tmp/source-integration-r120"):
            with self.subTest(output=output), self.assertRaises(ValueError):
                original.build(output, ROOT / "missing-manifest.json", ROOT / "missing-palette.yaml")


if __name__ == "__main__":
    unittest.main()
