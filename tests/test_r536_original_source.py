"""Offline controls for the exact original-cartridge-to-r536 source chain."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "scripts/diagnostics")]

import build_r536_candidate as builder


class R536OriginalSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r534 = (ROOT / "tmp/stage4-cache-key-r534/candidate.gb").read_bytes()

    def test_exact_ordered_overlay_chain(self):
        candidate, records = builder.apply_overlays(self.r534)
        self.assertEqual(hashlib.sha256(candidate).hexdigest(), builder.CONTRACT["candidate_sha256"])
        self.assertEqual([row["name"] for row in records], builder.CONTRACT["construction_order"])
        self.assertEqual([row["changed_byte_count"] for row in records], [143, 101, 52])
        self.assertEqual(records[0]["source_sha256"], builder.parent_builder.CONTRACT["candidate_sha256"])
        self.assertEqual(records[-1]["candidate_sha256"], builder.CONTRACT["candidate_sha256"])

    def test_unknown_parent_and_intermediate_mutations_fail_closed(self):
        mutated = bytearray(self.r534)
        mutated[0x100] ^= 1
        with self.assertRaises(ValueError):
            builder.apply_overlays(mutated)
        title = builder.title_menu.build(self.r534)
        title = bytearray(title)
        title[builder.stage_card.HOOK] ^= 1
        with self.assertRaises(ValueError):
            builder.stage_card.build(title)

    def _fake_parent(self, output: Path, palette: Path, *, write: bool = True) -> dict:
        if write:
            output.mkdir(parents=True)
            (output / "candidate.gb").write_bytes(self.r534)
            (output / "build-receipt.json").write_text("{}\n")
        return {
            "source_fingerprint": "unit-source",
            "original_rom": {"path": "original.gb", "sha256": "original"},
            "palette": {"path": str(palette.resolve()), "sha256": "palette"},
            "python": {"path": sys.executable, "sha256": "python"},
            "strace": {"path": "/usr/bin/strace", "sha256": "strace"},
        }

    def test_build_and_verifier_bind_retained_parent_and_overlay_evidence(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as container:
            output = Path(container) / "fresh-r536"
            palette = builder.DEFAULT_PALETTE
            parent = self._fake_parent

            def fake_build(path, selected_palette):
                self.assertEqual(selected_palette, palette.resolve())
                return parent(path, selected_palette)

            with patch.object(builder, "source_snapshot", return_value=("unit-source", [])), \
                 patch.object(builder.parent_builder, "build", side_effect=fake_build), \
                 patch.object(builder.parent_builder, "verify_receipt", side_effect=lambda p, r, y: parent(p.parent, y, write=False)):
                receipt = builder.build(output, palette)
                candidate = (output / "candidate.gb").read_bytes()
                self.assertEqual(hashlib.sha256(candidate).hexdigest(), builder.CONTRACT["candidate_sha256"])
                verified = builder.verify_receipt(output / "build-receipt.json", candidate, palette)
                self.assertEqual(verified, receipt)

                bad = copy.deepcopy(receipt)
                bad["construction"][0]["changed_byte_count"] += 1
                (output / "build-receipt.json").write_text(json.dumps(bad, indent=2) + "\n")
                with self.assertRaisesRegex(ValueError, "construction evidence differs"):
                    builder.verify_receipt(output / "build-receipt.json", candidate, palette)

    def test_output_must_be_fresh_and_repo_local(self):
        for output in (ROOT, ROOT / "tmp"):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, "fresh repository-local"):
                builder.build(output)


if __name__ == "__main__":
    unittest.main()
