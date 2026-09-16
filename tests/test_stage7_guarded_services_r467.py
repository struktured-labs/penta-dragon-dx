#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))
import compose_stage7_guarded_services_r467 as candidate


class GuardedServicesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = candidate.BASE.read_bytes()
        cls.built, cls.evidence = candidate.build(cls.source)

    def test_exact_scene_and_dcfd_routes(self) -> None:
        for scene in range(256):
            for dcfd in range(256):
                with self.subTest(scene=scene, dcfd=dcfd):
                    observed = candidate.model_guard(
                        candidate.GUARDED_STUB, scene=scene, dcfd=dcfd
                    )
                    expected = [] if scene == 8 else (
                        (["stage1_art_loader"] if dcfd else [])
                        + ["death_story_service"]
                    )
                    self.assertEqual(observed, expected)

    def test_selector_relocation_and_mirror_scope(self) -> None:
        def region(payload: bytes, bank: int, address: int, size: int) -> bytes:
            start = candidate.offset(bank, address)
            return payload[start:start + size]

        self.assertEqual(
            region(self.built, 13, candidate.NEW_SELECTOR_ADDR, 16),
            candidate.SELECTOR,
        )
        self.assertEqual(
            region(self.built, 13, candidate.OLD_SELECTOR_ADDR, 16),
            candidate.GUARDED_STUB,
        )
        self.assertEqual(
            region(self.built, 13, candidate.STAGE7_FRONT, 6),
            candidate.NEW_FRONT,
        )
        self.assertEqual(
            self.built[16 * 0x4000:17 * 0x4000],
            self.source[16 * 0x4000:17 * 0x4000],
        )
        self.assertTrue(self.evidence["bank16_unchanged"])

    def test_candidate_scope_and_reproducibility(self) -> None:
        artifact = candidate.OUT / "candidate.gb"
        self.assertTrue(artifact.is_file())
        self.assertEqual(artifact.read_bytes(), self.built)
        receipt = candidate.OUT / "build-receipt.json"
        self.assertTrue(receipt.is_file())
        self.assertEqual(hashlib.sha256(self.built).hexdigest(),
                         "a37791813dab654f6dc321697b288d3d2e9cbd9a5baa95645e45c3ca6eb48bcd")


if __name__ == "__main__":
    unittest.main()
