"""Source construction is independent of archived qualification observations."""
from dataclasses import replace
import importlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts/diagnostics"), str(ROOT / "scripts")]
import build_r534_source_prefix as prefix
import build_stage1_phase_content_key_r208 as r208
import build_stage1_split_phase_key_r209 as r209
import audit_stage7_dual_plane_hdma_r264 as dual_plane
import build_stage7_menu_signature_invalidation_r265 as r265
import build_stage7_transition_state_r269 as r269


class SourcePrefixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.factory_path = ROOT / "tmp/r534-palette-source-current494/build-1/factory.gb"
        if not cls.factory_path.is_file():
            raise unittest.SkipTest("exact factory-image fixture is unavailable")
        cls.factory = cls.factory_path.read_bytes()
        cls.r120, _ = prefix.baseline.build(cls.factory)
        cls.r199 = cls.r120
        for pin in prefix.phase.EARLY_STEPS:
            cls.r199, _ = importlib.import_module(pin.module).build(cls.r199)
        r210, _ = prefix.phase.construct(cls.r120)
        cls.r264, _ = prefix.stage2.build(r210)
        cls.dual_plane, _, _ = prefix.stage7.construct_dual_plane_source(dual_plane, cls.r264)
        cls.r265, _ = r265.construct(cls.dual_plane)

    def test_source_construction_never_invokes_corpus_checks(self):
        with patch.object(r208, "collect_traces", side_effect=AssertionError("archive dependency")), \
             patch.object(r208, "assess", side_effect=AssertionError("archive dependency")), \
             patch.object(r209, "transition_metrics", side_effect=AssertionError("archive dependency")):
            output, receipt = prefix.build(self.factory)
            self.assertEqual((output, receipt), prefix.build(self.factory))
        self.assertEqual(prefix.baseline.digest(output), prefix.stage4.OUTPUT_SHA256)
        self.assertEqual(len(receipt["phase"]["steps"]), 6)
        self.assertEqual(len(receipt["stage2_steps"]), 8)
        self.assertEqual(len(receipt["stage7"]["steps"]), 5)
        self.assertEqual(len(receipt["stage4"]["steps"]), 7)
        self.assertEqual(receipt["status"], "construction-only")
        for key in ("promotable", "historical_evidence_consumed",
                    "historical_transition_checks_rerun", "fresh_live_qualification"):
            self.assertIs(receipt[key], False)
            self.assertIs(receipt["phase"][key], False)

    def test_both_phase_entrypoints_agree_without_archives(self):
        early, _ = prefix.phase.construct(self.r120)
        later, receipt = prefix.phase.construct(self.r199)
        self.assertEqual(early, later)
        self.assertEqual(len(receipt["steps"]), 3)

    def test_historical_builds_still_require_their_corpora(self):
        with self.assertRaisesRegex(SystemExit, "no transition traces"):
            r208.build(self.r199, traces={})
        r208_image = r208.construct(self.r199)
        with self.assertRaisesRegex(SystemExit, "no transition traces"):
            r209.build(r208_image, traces={})
        with self.assertRaisesRegex(ValueError, "six historical traces"):
            prefix.phase.build(self.r120, {})

    def test_changed_inputs_and_recipes_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "factory identity"):
            prefix.build(self.factory[:-1])
        with self.assertRaisesRegex(ValueError, "exact r120 or r199"):
            prefix.phase.construct(self.r120[:-1])
        with self.assertRaisesRegex(SystemExit, "exact r199"):
            r208.construct(self.r199[:-1])
        r208_image = r208.construct(self.r199)
        with self.assertRaisesRegex(SystemExit, "exact r208"):
            r209.construct(r208_image[:-1])
        with patch.object(r208, "NEW_RUNTIME", r208.NEW_RUNTIME[:-1]):
            with self.assertRaisesRegex(SystemExit, "runtime length"):
                r208.construct(self.r199)
        with patch.object(r208, "OLD_RUNTIME", bytes(r208.RUNTIME_LENGTH)):
            with self.assertRaisesRegex(SystemExit, "preimage moved"):
                r208.construct(self.r199)
        with patch.object(r209, "OLD_RUNTIME", bytes(r209.RUNTIME_LENGTH)):
            with self.assertRaisesRegex(SystemExit, "preimage moved"):
                r209.construct(r208_image)
        with patch.object(r209, "PRIVATE_OFFSET", 0):
            with self.assertRaisesRegex(SystemExit, "cave is no longer erased"):
                r209.construct(r208_image)
        with patch.object(r209, "build_gateway", return_value=bytes(r209.RUNTIME_LENGTH)):
            with self.assertRaisesRegex(ValueError, "generated ROM differs"):
                prefix.phase.construct(self.r199)

    def test_phase_output_and_static_receipt_pins_remain_mandatory(self):
        pin = prefix.phase.STEPS[0]
        with patch.object(prefix.phase, "STEPS", (replace(pin, rom="0" * 64), *prefix.phase.STEPS[1:])):
            with self.assertRaisesRegex(ValueError, "generated ROM differs"):
                prefix.phase.construct(self.r199)
        pin = prefix.phase.EARLY_STEPS[0]
        with patch.object(prefix.phase, "EARLY_STEPS", (replace(pin, receipt="0" * 64), *prefix.phase.EARLY_STEPS[1:])):
            with self.assertRaisesRegex(ValueError, "static receipt differs"):
                prefix.phase.construct(self.r120)

    def test_stage7_construction_does_not_call_historical_audits(self):
        with patch.object(r265, "static_contract", side_effect=AssertionError("historical audit")), \
             patch.object(r265, "build", side_effect=AssertionError("historical audit")), \
             patch.object(r269, "install", side_effect=AssertionError("historical audit")), \
             patch.object(r269, "rebind_static_receipt", side_effect=AssertionError("historical audit")), \
             patch.object(Path, "read_bytes", side_effect=AssertionError("artifact read")):
            result, receipt = prefix.stage7.construct(self.r264)
            self.assertEqual((result, receipt), prefix.stage7.construct(self.r264))
        self.assertEqual(prefix.baseline.digest(result), prefix.stage7.OUTPUT_SHA256)
        self.assertEqual(len(receipt["steps"]), 5)
        self.assertEqual(len(receipt["steps"][0]["source_contracts"]), 11)
        for key in ("promotable", "historical_evidence_consumed",
                    "historical_corpora_rechecked", "fresh_live_qualification"):
            self.assertIs(receipt[key], False)
        for step in receipt["steps"][1:3]:
            contract = step["source_contracts"]
            self.assertEqual(contract["status"], "construction-only")
            self.assertNotIn("patrol_evidence", contract)
            self.assertNotIn("base_static_receipt_sha256", contract)

    def test_stage7_historical_audits_still_reject_missing_receipts(self):
        with self.assertRaisesRegex(ValueError, "two historical static receipts"):
            prefix.stage7.build(self.r264, {})
        with self.assertRaisesRegex(AssertionError, "static receipt changed"):
            r265.build(self.dual_plane, base_receipt=b"", control=self.r264)
        with self.assertRaisesRegex(AssertionError, "static template changed"):
            r269.install(self.r265, self.r264, Path("not-written.gb"), b"")
        history_path = ROOT / prefix.stage7.HISTORICAL_INPUTS["stage7_dual_plane_static"][0]
        with self.assertRaisesRegex(AssertionError, "control is missing or changed"):
            r265.build(self.dual_plane, base_receipt=history_path.read_bytes(), control=b"")

    def test_stage7_input_and_output_pins_remain_mandatory(self):
        with self.assertRaisesRegex(ValueError, "exact repaired r264"):
            prefix.stage7.construct(self.r264[:-1])
        with self.assertRaisesRegex(AssertionError, "wrong frozen"):
            r265.construct(self.dual_plane[:-1])
        with self.assertRaisesRegex(AssertionError, "wrong exact r265"):
            r269.construct(self.r265[:-1], self.r264)
        with self.assertRaisesRegex(AssertionError, "wrong exact r264"):
            r269.construct(self.r265, self.r264[:-1])
        for index, pin in enumerate(prefix.stage7.STEPS):
            broken = list(prefix.stage7.STEPS)
            broken[index] = replace(pin, rom="0" * 64)
            with self.subTest(pin=pin.module), patch.object(prefix.stage7, "STEPS", tuple(broken)):
                with self.assertRaisesRegex(ValueError, "generated ROM differs"):
                    prefix.stage7.construct(self.r264)
        with patch.object(prefix.stage7, "STEPS", prefix.stage7.STEPS[:-1]):
            with self.assertRaisesRegex(ValueError, "did not reproduce exact r273"):
                prefix.stage7.construct(self.r264)

    def test_stage7_recipe_preimages_and_semantic_controls_remain_mandatory(self):
        cases = (("OLD_HELPER", bytes(len(r265.OLD_HELPER)), "preimage changed"),
                 ("NEW_HELPER", r265.NEW_HELPER[:-1], "helper width"),
                 ("NEXT_HELPER", bytes(len(r265.NEXT_HELPER)), "boundary changed"),
                 ("CALLSITE_CONTRACT", bytes(len(r265.CALLSITE_CONTRACT)), "caller changed"),
                 ("VBLANK_MAPPER_CONTRACT", bytes(len(r265.VBLANK_MAPPER_CONTRACT)), "maps bank13"))
        for name, value, error in cases:
            with self.subTest(name=name), patch.object(r265, name, value):
                with self.assertRaisesRegex(AssertionError, error):
                    r265.construct(self.dual_plane)
        with patch.object(r265, "helper_semantics", return_value={"z": False, "a": 1, "invalidate": True}):
            with self.assertRaisesRegex(AssertionError, "semantic negative control"):
                r265.construct(self.dual_plane)
        with patch.object(r265, "timing_contract", return_value={"FFE4_zero_all_scenes": {"delta": 1}}):
            with self.assertRaisesRegex(AssertionError, "hot path changed"):
                r265.construct(self.dual_plane)
        with patch.object(r269, "OLD_HELPER_SHA256", "0" * 64):
            with self.assertRaisesRegex(AssertionError, "helper changed"):
                r269.construct(self.r265, self.r264)
        with patch.object(dual_plane, "DESCRIPTORS", dual_plane.HELPER):
            with self.assertRaisesRegex(ValueError, "overlaps descriptor"):
                prefix.stage7.construct(self.r264)

    def test_stage7_source_contracts_cannot_be_silently_weakened(self):
        for revision in prefix.stage7.SOURCE_CONTRACT_SHA256:
            changed = {**prefix.stage7.SOURCE_CONTRACT_SHA256, revision: "0" * 64}
            with self.subTest(revision=revision), patch.object(prefix.stage7, "SOURCE_CONTRACT_SHA256", changed):
                with self.assertRaisesRegex(ValueError, "contract receipt differs"):
                    prefix.stage7.construct(self.r264)
        with patch.object(dual_plane, "guard_contract", return_value={}):
            with self.assertRaisesRegex(ValueError, "contract receipt differs"):
                prefix.stage7.construct(self.r264)

    def test_stage7_static_receipt_pins_remain_mandatory(self):
        for index in (0, 3, 4):
            broken = list(prefix.stage7.STEPS)
            broken[index] = replace(broken[index], receipt="0" * 64)
            with self.subTest(index=index), patch.object(prefix.stage7, "STEPS", tuple(broken)):
                with self.assertRaisesRegex(ValueError, "static receipt differs"):
                    prefix.stage7.construct(self.r264)

    def test_full_lineage_joins_with_only_five_inputs_and_no_artifact_reads(self):
        program = r'''
import json, sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
factory = Path(sys.argv[2]).read_bytes()
original_path = root / "rom/Penta Dragon (J).gb"
original = original_path.read_bytes()
paths = json.loads((root / "tmp/r534-lineage-inputs-current486.json").read_text())
# Do not load the phase, Stage-7, or Stage-4 historical inputs.
evidence = {name: (root / path).read_bytes() for name, path in paths.items()
            if not name.startswith(("phase_", "stage7_", "stage4_"))}
assert len(evidence) == 5
sys.path[:0] = [str(root / "scripts/diagnostics"), str(root / "scripts"), sys.argv[3]]
def audit(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)):
        raw = args[0].decode() if isinstance(args[0], bytes) else args[0]
        path = (root / raw).resolve()
        if path.is_relative_to(root / "tmp") or path == original_path:
            raise AssertionError(f"unexpected artifact read: {path}")
sys.addaudithook(audit)
import build_r534_source_prefix as prefix
import rebuild_r534_lineage as lineage
first = None
for _ in range(2):
    intermediate, construction = prefix.build(factory)
    rom, historical = lineage.build(intermediate, original_rom=original, historical_evidence=evidence)
    item = (rom, construction, historical)
    if first is not None: assert item == first
    first = item
    assert lineage.digest(rom) == lineage.CANDIDATE_SHA256
    assert len(historical["steps"]) == 79
    assert not construction["historical_evidence_consumed"]
    assert not construction["stage7"]["historical_evidence_consumed"]
    assert not construction["stage4"]["historical_evidence_consumed"]
    assert len(historical["historical_evidence"]) == 5
print(json.dumps({"candidate_sha256": lineage.digest(first[0]), "double_build_identical": True,
                  "phase_historical_inputs_read": 0, "stage7_historical_inputs_read": 0,
                  "stage4_historical_inputs_read": 0, "remaining_historical_inputs": 5}))
'''
        run = subprocess.run([sys.executable, "-I", "-B", "-c", program, str(ROOT),
                              str(self.factory_path), str(Path(yaml.__file__).resolve().parent.parent)],
                             cwd=ROOT, capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        result = json.loads(run.stdout)
        self.assertTrue(result["double_build_identical"])
        self.assertEqual(result["phase_historical_inputs_read"], 0)
        self.assertEqual(result["stage7_historical_inputs_read"], 0)
        self.assertEqual(result["stage4_historical_inputs_read"], 0)
        self.assertEqual(result["remaining_historical_inputs"], 5)


if __name__ == "__main__":
    unittest.main()
