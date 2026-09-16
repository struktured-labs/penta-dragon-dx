"""ROM-free controls for the source-built restart fix, issues #7–#10."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "scripts/diagnostics")]
import build_restart_candidate as builder
import restart_source_profile as profile


class RestartOriginalSourceTests(unittest.TestCase):
    def test_exact_pinned_lineage_and_no_implicit_approval(self):
        self.assertEqual(builder.CONTRACT["candidate_sha256"],
                         "c693eafb50e7872fa884d0d26ce3fbfd4f2fac0dba246ff738931643e7f0ba5d")
        self.assertEqual(builder.row_guard.BASE_SHA,
                         builder.parent_builder.CONTRACT["candidate_sha256"])
        self.assertEqual(builder.row_guard.CANDIDATE_SHA, builder.spike_death.PARENT)
        self.assertEqual(builder.spike_death.CANDIDATE_SHA,
                         builder.CONTRACT["candidate_sha256"])
        self.assertFalse(builder.CONTRACT["release_qualification"])
        self.assertFalse(builder.CONTRACT["audience_approval_recorded"])
        with self.assertRaises(ValueError):
            builder.apply_overlays(b"unknown parent")

    def test_receipt_rejects_tampered_evidence(self):
        original, candidate = b"parent", b"fixed!"
        records = [{"name": "unit-only", "changed_byte_count": 6}]
        snapshot = ("unit-source", [])
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as scratch:
            output = Path(scratch) / "new"
            palette = builder.DEFAULT_PALETTE
            parent = {
                "source_fingerprint": snapshot[0],
                "original_rom": {"sha256": "original"},
                "palette": {"sha256": "palette"},
                "python": {"sha256": "python"},
                "strace": {"sha256": "strace"},
            }

            def build_parent(path, selected_palette):
                self.assertEqual(selected_palette, palette.resolve())
                path.mkdir(parents=True)
                (path / "candidate.gb").write_bytes(original)
                (path / "build-receipt.json").write_text("{}\n")
                return parent

            with patch.object(builder, "source_snapshot", return_value=snapshot), \
                 patch.object(builder.parent_builder, "build", side_effect=build_parent), \
                 patch.object(builder.parent_builder, "verify_receipt", return_value=parent), \
                 patch.object(builder, "apply_overlays", return_value=(candidate, records)), \
                 patch.dict(builder.CONTRACT, candidate_sha256=builder.digest(candidate)):
                receipt = builder.build(output)
                path = output / "build-receipt.json"
                self.assertEqual(builder.verify_receipt(path, candidate), receipt)
                mutations = (
                    ("construction", []),
                    ("source_fingerprint", "stale"),
                    ("source_files", [{"path": "unexpected"}]),
                    ("source_parent", {**receipt["source_parent"], "receipt_sha256": "wrong"}),
                    ("palette", {"sha256": "wrong"}),
                    ("release_qualification", True),
                    ("retained_candidate_roms_read", 0),
                )
                for name, value in mutations:
                    with self.subTest(name=name):
                        bad = copy.deepcopy(receipt)
                        bad[name] = value
                        path.write_text(json.dumps(bad))
                        with self.assertRaises(ValueError):
                            builder.verify_receipt(path, candidate)
                path.write_text(json.dumps(receipt))
                binding = {"receipt": str(path.resolve()),
                           "receipt_sha256": builder.digest(path.read_bytes()),
                           "source_fingerprint": snapshot[0]}
                self.assertEqual(profile.verify_binding(binding, candidate, palette), receipt)
                for key in binding:
                    with self.subTest(binding_key=key):
                        bad = dict(binding)
                        bad[key] = "wrong"
                        with self.assertRaises((ValueError, OSError)):
                            profile.verify_binding(bad, candidate, palette)
                (output / "candidate.gb").write_bytes(b"tamper")
                with self.assertRaises(ValueError):
                    builder.verify_receipt(path, candidate)

    def test_output_must_be_fresh_and_repo_local(self):
        for output in (ROOT, ROOT / "tmp"):
            with self.subTest(output=output), self.assertRaises(ValueError):
                builder.build(output)
