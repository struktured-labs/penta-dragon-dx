"""#67: alignment and omissions must not manufacture a deterministic pass."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "low_health_pair", ROOT / "scripts/diagnostics/verify_low_health_hazard_determinism.py")
PAIR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PAIR)


class ExactCorpus(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.scratch = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.addCleanup(self.scratch.cleanup)
        self.first, self.second = [Path(self.scratch.name) / name for name in ("a", "b")]
        for directory in (self.first, self.second):
            directory.mkdir()
            self.write(directory, [1, 2, 3])

    def write(self, directory, values):
        (directory / "low-health.frames.tsv").write_text(
            "sample\tframe\thealth_phase\thp_main\n" + "".join(
                f"{i}\t{value}\tpre\tFF\n" for i, value in enumerate(values, 1)))
        for i, value in enumerate(values, 1):
            (directory / f"low-health.frame{i:04d}.png").write_bytes(bytes([value]))

    def compare(self):
        return PAIR.exact_corpus_comparison(self.first, self.second, 3)

    def test_identical_full_corpus_passes(self):
        self.assertTrue(self.compare()["passed"])

    def test_shifted_sequence_fails(self):
        self.write(self.second, [2, 3, 4])
        result = self.compare()
        self.assertFalse(result["passed"])
        self.assertEqual(result["image_mismatch_samples"], [1, 2, 3])

    def test_health_fields_are_not_masked(self):
        path = self.second / "low-health.frames.tsv"
        path.write_text(path.read_text().replace("pre\tFF", "warning\t40", 1))
        self.assertEqual(self.compare()["row_mismatch_samples"], [1])
        self.assertFalse(self.compare()["passed"])

    def test_missing_image_fails(self):
        (self.second / "low-health.frame0002.png").unlink()
        self.assertFalse(self.compare()["passed"])

    def test_extra_frame_is_not_cropped(self):
        self.write(self.second, [1, 2, 3, 4])
        self.assertFalse(self.compare()["passed"])

    def test_equal_truncated_corpora_fail(self):
        for directory in (self.first, self.second):
            self.write(directory, [1, 2])
            (directory / "low-health.frame0003.png").unlink()
        self.assertFalse(self.compare()["passed"])

    def test_publication_tail_is_compared(self):
        for directory in (self.first, self.second):
            self.write(directory, [1, 2, 3, 4])
        self.assertTrue(self.compare()["passed"])
        (self.second / "low-health.frame0004.png").write_bytes(b"bad")
        self.assertFalse(self.compare()["passed"])

    def test_unaccounted_image_fails(self):
        (self.second / "low-health.frame9999.png").write_bytes(b"extra")
        self.assertFalse(self.compare()["passed"])


if __name__ == "__main__":
    unittest.main()
