"""The public archive must remain deterministic and ROM-free."""

from __future__ import annotations

import tempfile
from pathlib import Path
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "scripts"))
import build_release_bundle as bundle


class ReleaseBundleArchiveContractTests(unittest.TestCase):
    def test_packaged_readme_names_the_authoritative_gate_count(self) -> None:
        for count in (bundle.EXPECTED_GATE_COUNT, 97):
            rendered = bundle.render_readme(False, dict(
                size=1048576, md5='m', sha1='s1', sha256='s256', crc32='crc'), count)
            normalized = " ".join(rendered.decode().split())
            self.assertIn(f"passed all {count} serial emulator release gates", normalized)
            self.assertNotIn("33 isolated emulator release gates", normalized)

    def test_zip_bytes_metadata_and_order_are_deterministic(self) -> None:
        files = {
            "README.txt": b"release notes\n",
            "Penta_Dragon_DX_v3.01.ips": b"PATCH",
            "CHECKSUMS.txt": b"checksums\n",
        }
        with tempfile.TemporaryDirectory(
            prefix="release-archive-contract-", dir=ROOT / "tmp"
        ) as scratch:
            scratch_path = Path(scratch)
            self.assertTrue(scratch_path.is_relative_to(ROOT / "tmp"))
            first = scratch_path / "first.zip"
            second = scratch_path / "second.zip"
            bundle.write_deterministic_zip(first, "release", files)
            bundle.write_deterministic_zip(second, "release", files)

            self.assertEqual(first.read_bytes(), second.read_bytes())
            bundle.validate_archive(first, files, "release")
            with zipfile.ZipFile(first) as archive:
                entries = archive.infolist()
                self.assertEqual(
                    [entry.filename for entry in entries],
                    [f"release/{name}" for name in sorted(files)],
                )
                for entry in entries:
                    self.assertEqual(entry.date_time, (1980, 1, 1, 0, 0, 0))
                    self.assertEqual(entry.create_system, 3)
                    self.assertEqual(entry.external_attr >> 16, 0o100644)

    def test_archive_validator_rejects_rom_save_and_state_payloads(self) -> None:
        for filename in (
            "candidate.gb",
            "candidate.gbc",
            "candidate.gba",
            "run.sav",
            "run.ss",
            "run.ss0",
            "run.ss4",
        ):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory(
                prefix="release-forbidden-contract-", dir=ROOT / "tmp"
            ) as scratch:
                path = Path(scratch) / "forbidden.zip"
                files = {filename: b"forbidden"}
                bundle.write_deterministic_zip(path, "release", files)
                with self.assertRaisesRegex(
                    SystemExit, "forbidden ROM/save artifact"
                ):
                    bundle.validate_archive(path, files, "release")

    def test_archive_validator_rejects_unlisted_and_changed_payloads(self) -> None:
        files = {"README.txt": b"expected\n"}
        with tempfile.TemporaryDirectory(
            prefix="release-tamper-contract-", dir=ROOT / "tmp"
        ) as scratch:
            scratch_path = Path(scratch)
            extra = scratch_path / "extra.zip"
            bundle.write_deterministic_zip(
                extra,
                "release",
                {**files, "UNLISTED.txt": b"unexpected\n"},
            )
            with self.assertRaisesRegex(SystemExit, "allowlist"):
                bundle.validate_archive(extra, files, "release")

            changed = scratch_path / "changed.zip"
            bundle.write_deterministic_zip(
                changed, "release", {"README.txt": b"changed\n"}
            )
            with self.assertRaisesRegex(SystemExit, "payload changed"):
                bundle.validate_archive(changed, files, "release")


if __name__ == "__main__":
    unittest.main()
