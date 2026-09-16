"""Source-only Stage-4 construction retains guards without fabricating evidence."""
from dataclasses import replace
import importlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts/diagnostics"), str(ROOT / "scripts")]
import r534_stage4_ancestry as stage4
import build_stage4_lazy_departure_r285 as r285
import build_stage4_lazy_departure_r286 as r286
import build_stage4_menu_exit_invalidation_r287 as r287


class Stage4SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = ROOT / "tmp/r534-source-prefix-current500/intermediate-r273.gb"
        if not source.is_file():
            raise unittest.SkipTest("exact source-prefix fixture is unavailable")
        cls.source = source.read_bytes()
        result = cls.source
        for pin in stage4.STEPS[:4]:
            result, _ = importlib.import_module(pin.module).install(result)
            setattr(cls, pin.module.rsplit("_", 1)[1], result)
        cls.r285, _ = r285.construct(cls.r281, cls.r279)
        cls.r286, _ = r286.construct(cls.r285, cls.r281, cls.r279)

    def test_no_historical_audits_or_artifact_reads_and_no_observation_claims(self):
        with patch.object(r285, "verify_corpora", side_effect=AssertionError("corpus read")), \
             patch.object(r285, "verify_wram_ownership", side_effect=AssertionError("WRAM read")), \
             patch.object(r285, "install", side_effect=AssertionError("historical audit")), \
             patch.object(r286, "install", side_effect=AssertionError("historical audit")), \
             patch.object(r287, "static_contract", side_effect=AssertionError("historical audit")), \
             patch.object(r287, "build", side_effect=AssertionError("historical audit")), \
             patch.object(Path, "read_bytes", side_effect=AssertionError("artifact read")):
            output, receipt = stage4.construct(self.source)
            self.assertEqual((output, receipt), stage4.construct(self.source))
        self.assertEqual(stage4.digest(output), stage4.OUTPUT_SHA256)
        self.assertEqual(len(receipt["steps"]), 7)
        for key in ("promotable", "historical_evidence_consumed", "historical_corpora_rechecked",
                    "historical_wram_snapshots_checked", "fresh_live_qualification"):
            self.assertIs(receipt[key], False)
        encoded = json.dumps(receipt)
        for forbidden in ("wram_ownership", "corpus_contract", "bound_corpora", "bound_snapshot",
                          "measured_stage4_decisions", "projected_route_saving", "projected_saving",
                          "bound_decisions", "zero_in_bound", "zero_collision_variant"):
            self.assertNotIn(forbidden, encoded)
        for step in receipt["steps"][4:]:
            self.assertEqual(step["source_contracts"]["status"], "construction-only")
            self.assertIs(step["source_contracts"]["historical_evidence_consumed"], False)
        self.assertEqual(receipt["steps"][4]["reference_sha256"], {"r279": stage4.digest(self.r279)})
        self.assertEqual(receipt["steps"][5]["reference_sha256"],
                         {"r281": stage4.digest(self.r281), "r279": stage4.digest(self.r279)})

    def test_historical_entrypoints_still_require_evidence_and_receipts(self):
        with self.assertRaisesRegex(ValueError, "fifteen historical inputs"):
            stage4.build(self.source, {})
        with self.assertRaisesRegex(AssertionError, "missing explicit historical input"):
            r285.install(self.r281, self.r279, evidence={})
        with self.assertRaisesRegex(AssertionError, "receipt identity changed"):
            r286.install(self.r285, self.r281, self.r279, b"", evidence={})
        historical = (ROOT / "tmp/stage4-lazy-departure-r285/build-receipt.json").read_bytes()
        with self.assertRaisesRegex(AssertionError, "missing explicit historical input"):
            r286.install(self.r285, self.r281, self.r279, historical, evidence={})
        with self.assertRaisesRegex(AssertionError, "receipt identity changed"):
            r287.build(self.r286, b"")

    def test_changed_inputs_and_generated_references_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "exact r273"):
            stage4.construct(self.source[:-1])
        for args in ((self.r281[:-1], self.r279), (self.r281, self.r279[:-1])):
            with self.subTest(builder="r285"), self.assertRaises(AssertionError):
                r285.construct(*args)
        for index in range(3):
            args = [self.r285, self.r281, self.r279]
            args[index] = args[index][:-1]
            with self.subTest(builder="r286", index=index), self.assertRaises(AssertionError):
                r286.construct(*args)
        with self.assertRaisesRegex(AssertionError, "512 KiB"):
            r287.construct(self.r286[:-1])

    def test_every_rom_static_and_source_contract_pin_is_required(self):
        for index, pin in enumerate(stage4.STEPS):
            changed = list(stage4.STEPS)
            changed[index] = replace(pin, rom="0" * 64)
            with self.subTest(rom=pin.module), patch.object(stage4, "STEPS", tuple(changed)):
                with self.assertRaisesRegex(ValueError, "generated ROM differs"):
                    stage4.construct(self.source)
            if index < 4:
                changed[index] = replace(pin, receipt="0" * 64)
                with self.subTest(receipt=pin.module), patch.object(stage4, "STEPS", tuple(changed)):
                    with self.assertRaisesRegex(ValueError, "contract receipt differs"):
                        stage4.construct(self.source)
        for revision in stage4.SOURCE_CONTRACT_SHA256:
            changed = {**stage4.SOURCE_CONTRACT_SHA256, revision: "0" * 64}
            with self.subTest(source=revision), patch.object(stage4, "SOURCE_CONTRACT_SHA256", changed):
                with self.assertRaisesRegex(ValueError, "contract receipt differs"):
                    stage4.construct(self.source)
        with patch.object(stage4, "SOURCE_CONTRACT_SHA256", {}):
            with self.assertRaisesRegex(ValueError, "pin inventory differs"):
                stage4.construct(self.source)
        with patch.object(stage4, "STEPS", stage4.STEPS[:-1]):
            with self.assertRaisesRegex(ValueError, "did not reproduce exact r287"):
                stage4.construct(self.source)

    def test_emitter_width_preimage_delta_and_semantic_guards_are_required(self):
        with patch.object(r285, "build_wram_block", return_value=b""):
            with self.assertRaisesRegex(AssertionError, "WRAM block width"):
                r285.construct(self.r281, self.r279)
        with patch.object(r285, "TRAMPOLINE_PAYLOAD_ADDR", r285.TRAMPOLINE_PAYLOAD_ADDR + 1):
            with self.assertRaisesRegex(AssertionError, "trampoline payload"):
                r285.construct(self.r281, self.r279)
        with patch.object(r285, "EXPECTED_CHANGED_BYTES", r285.EXPECTED_CHANGED_BYTES + 1):
            with self.assertRaisesRegex(AssertionError, "changed-byte count"):
                r285.construct(self.r281, self.r279)
        with patch.object(r286, "build_installer", return_value=b""):
            with self.assertRaisesRegex(AssertionError, "installer shrink"):
                r286.construct(self.r285, self.r281, self.r279)
        with patch.object(r287, "OLD_HELPER", bytes(len(r287.OLD_HELPER))):
            with self.assertRaisesRegex(AssertionError, "preimage changed"):
                r287.construct(self.r286)
        with patch.object(r287, "NEW_HELPER", r287.NEW_HELPER[:-1]):
            with self.assertRaisesRegex(AssertionError, "width changed"):
                r287.construct(self.r286)
        with patch.object(r287, "new_semantics", return_value={"z": True, "a": 0, "invalidate": False, "path": "closed"}):
            with self.assertRaisesRegex(AssertionError, "caller-Z mismatch"):
                r287.construct(self.r286)

    def test_source_contract_metadata_cannot_silently_lose_checks(self):
        with patch.object(r285, "verify_base", return_value={}):
            with self.assertRaisesRegex(ValueError, "contract receipt differs"):
                stage4.construct(self.source)
        with patch.object(r287, "timing_contract", return_value={}):
            with self.assertRaisesRegex(ValueError, "contract receipt differs"):
                stage4.construct(self.source)


if __name__ == "__main__":
    unittest.main()
