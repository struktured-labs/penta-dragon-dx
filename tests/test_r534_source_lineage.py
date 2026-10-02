"""Exact retained-input replay with explicit evidence and no saved intermediates."""
from __future__ import annotations

import hashlib
import importlib
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts/diagnostics"), str(ROOT / "scripts")]
import rebuild_r534_lineage as lineage


class SourceLineageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = ROOT / "tmp/stage1-subscene-tracking-r442/candidate.gb"
        if not base.is_file():
            raise unittest.SkipTest("retained exact r442 input is unavailable")
        cls.source = base.read_bytes()

    def test_double_build_without_any_intermediate_artifact_access(self):
        program = r'''
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
scratch = root / "tmp"
source = (scratch / sys.argv[3] / "candidate.gb").read_bytes()
original_path = root / "rom/Penta Dragon (J).gb"
inputs = {}
if sys.argv[3] == "stage1-scene0b-publication-commit-r314":
    inputs = {"base_receipt": (scratch / sys.argv[3] / "build-receipt.json").read_bytes(),
              "original_rom": original_path.read_bytes()}
elif sys.argv[3] in ("stage4-menu-exit-invalidation-r287", "stage7-skip-invisible-padding-r273",
                    "stage1-menu-hidden-repair-r264", "stage1-deferred-palette-r210",
                    "stage1-stale-window-hide-r199", "source-integration-r120"):
    inputs = {"original_rom": original_path.read_bytes(),
              "historical_evidence": {name: (root / path).read_bytes()
                                      for name, path in json.loads(sys.argv[5]).items()}}
def audit(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)):
        path = Path(args[0].decode() if isinstance(args[0], bytes) else args[0]).resolve()
        if path.is_relative_to(scratch) or path == original_path:
            raise RuntimeError(f"build accessed an intermediate scratch artifact: {path}")
sys.addaudithook(audit)
# -I excludes user-site dependencies; add the installed PyYAML location
# explicitly without enabling environment/PYTHONPATH or scratch imports.
sys.path.append(sys.argv[2])
sys.path[:0] = [str(root / "scripts/diagnostics"), str(root / "scripts")]
import rebuild_r534_lineage as lineage
from suite_contract import source_paths
result, receipt = lineage.build(source, **inputs)
again, second = lineage.build(source, **inputs)
assert (result, receipt) == (again, second)
assert Path(lineage.__file__).resolve() in set(source_paths())
assert Path(lineage.prefix.__file__).resolve() in set(source_paths())
assert Path(lineage.ancestry.__file__).resolve() in set(source_paths())
assert Path(lineage.stage4.__file__).resolve() in set(source_paths())
assert Path(lineage.stage7.__file__).resolve() in set(source_paths())
assert Path(lineage.stage2.__file__).resolve() in set(source_paths())
assert Path(lineage.phase.__file__).resolve() in set(source_paths())
assert receipt["promotable"] is False
assert len(receipt["steps"]) == int(sys.argv[4])
assert receipt["base_sha256"] == hashlib.sha256(source).hexdigest()
last = receipt["base_sha256"]
generated_roms = set()
generated_receipt = hashlib.sha256(inputs["base_receipt"]).hexdigest() if "base_receipt" in inputs else None
assert receipt["base_receipt_sha256"] == generated_receipt
assert receipt["original_rom_sha256"] == (hashlib.sha256(inputs["original_rom"]).hexdigest() if inputs else None)
for step in receipt["steps"]:
    assert step["base_sha256"] == last
    for reference in step.get("generated_references", {}).values():
        assert reference in generated_roms
    for name, reference in step.get("reference_sha256", {}).items():
        assert reference == receipt["base_sha256"] if name.startswith("retained_") else reference in generated_roms
    generated_roms.add(step["candidate_sha256"])
    if step.get("input_receipt_sha256"):
        assert step["input_receipt_sha256"] == generated_receipt
    generated_receipt = step.get("generated_receipt_sha256")
    last = step["candidate_sha256"]
assert last == hashlib.sha256(result).hexdigest()
history = inputs.get("historical_evidence", {})
assert set(receipt["historical_evidence"]) == set(history)
for name, data in history.items():
    assert receipt["historical_evidence"][name] == {
        "sha256": hashlib.sha256(data).hexdigest(), "fresh_live_qualification": False}
assert len(receipt["component_builds"]) == bool(history)
if history:
    side = receipt["component_builds"][0]
    producer = next(step for step in receipt["steps"] if step["candidate_sha256"] == side["base_sha256"])
    assert side["input_receipt_sha256"] == producer["generated_receipt_sha256"]
    merge = next(step for step in receipt["steps"] if step.get("generated_component"))
    assert merge["generated_component"] == {
        "candidate_sha256": side["candidate_sha256"],
        "build_receipt_sha256": side["generated_receipt_sha256"]}
print(json.dumps({"sha256": last, "double_build_identical": True}))
'''
        for base, count in (("stage1-subscene-tracking-r442", 10),
                            ("stage1-hazard-terminal-silhouette-r343", 60),
                            ("stage1-scene0b-publication-commit-r314", 68),
                            ("stage4-menu-exit-invalidation-r287", 79),
                            ("stage7-skip-invisible-padding-r273", 86),
                            ("stage1-menu-hidden-repair-r264", 91),
                            ("stage1-deferred-palette-r210", 99),
                            ("stage1-stale-window-hide-r199", 102),
                            ("source-integration-r120", 105)):
            with self.subTest(base=base):
                history = dict(lineage.ancestry.HISTORICAL_INPUTS)
                if count >= 86:
                    history.update(lineage.stage4.HISTORICAL_INPUTS)
                if count >= 91:
                    history.update(lineage.stage7.HISTORICAL_INPUTS)
                if count >= 102:
                    history.update(lineage.phase.HISTORICAL_INPUTS)
                result = subprocess.run(
                    [sys.executable, "-I", "-B", "-c", program, str(ROOT),
                     str(Path(yaml.__file__).resolve().parents[1]), base, str(count),
                     json.dumps({name: path for name, (path, _) in history.items()})],
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), {
                    "sha256": lineage.CANDIDATE_SHA256,
                    "double_build_identical": True,
                })

    def test_wrong_base_rejected_before_composition(self):
        damaged = bytearray(self.source)
        damaged[0x14F] ^= 1
        with patch.object(lineage, "STEPS", ()):
            with self.assertRaisesRegex(ValueError, "exact retained r120, r199, r210, r264, r273, r287, r314, r343, or r442"):
                lineage.build(bytes(damaged))

    def test_prefix_pins_match_independent_bank24_ownership_history(self):
        from expansion_bank24_r455 import CHAIN
        prefix_steps = {step.module: step for step in lineage.prefix.STEPS}
        for module, _, expected in CHAIN[:-1]:
            self.assertEqual(prefix_steps[module].output_sha256, expected)
        self.assertEqual(len(prefix_steps), 50)
        self.assertEqual(lineage.prefix.OUTPUT_SHA256, lineage.BASE_SHA256)

    def test_generated_receipt_corruption_rejects_without_saved_fallback(self):
        source = (ROOT / "tmp/stage1-hazard-terminal-silhouette-r343/candidate.gb").read_bytes()
        with patch.object(lineage.prefix, "serialize_receipt", return_value=b"{}\n"):
            with self.assertRaisesRegex(ValueError, "generated input receipt hash differs"):
                lineage.build(source)

    def test_incomplete_prefix_and_wrong_prefix_input_reject(self):
        source = (ROOT / "tmp/stage1-hazard-terminal-silhouette-r343/candidate.gb").read_bytes()
        with patch.object(lineage.prefix, "STEPS", ()):
            with self.assertRaisesRegex(ValueError, "did not reproduce exact r442"):
                lineage.prefix.build(source)
        with self.assertRaisesRegex(ValueError, "exact retained r314 or r343"):
            lineage.prefix.build(self.source)

    def test_early_inputs_are_required_and_hash_pinned(self):
        base = ROOT / "tmp/stage1-scene0b-publication-commit-r314"
        source = (base / "candidate.gb").read_bytes()
        receipt = (base / "build-receipt.json").read_bytes()
        stock = (ROOT / "rom/Penta Dragon (J).gb").read_bytes()
        for inputs, error in (
            ({}, "exact retained static build receipt"),
            ({"base_receipt": b"{}", "original_rom": stock}, "exact retained static build receipt"),
            ({"base_receipt": receipt}, "exact original cartridge"),
            ({"base_receipt": receipt, "original_rom": stock[:-1]}, "exact original cartridge"),
        ):
            with self.subTest(error=error, inputs=list(inputs)):
                with self.assertRaisesRegex(ValueError, error):
                    lineage.build(source, **inputs)
        with self.assertRaisesRegex(ValueError, "does not consume extra"):
            lineage.build(self.source, base_receipt=receipt)

    def test_missing_final_steps_cannot_claim_r534(self):
        with patch.object(lineage, "STEPS", ()):
            with self.assertRaisesRegex(ValueError, "did not reproduce exact r534"):
                lineage.build(self.source)

    def test_historical_live_inputs_are_exact_and_never_optional(self):
        ancestry = lineage.ancestry
        source = (ROOT / "tmp/stage4-menu-exit-invalidation-r287/candidate.gb").read_bytes()
        evidence = {name: (ROOT / path).read_bytes()
                    for name, (path, _) in ancestry.HISTORICAL_INPUTS.items()}
        for changed in ({}, {**evidence, "unrequested": b"{}"}):
            with self.assertRaisesRegex(ValueError, "exactly the five historical"):
                ancestry.build(source, changed)
        for name in evidence:
            changed = {**evidence, name: evidence[name] + b" "}
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "historical evidence identity differs"):
                    ancestry.build(source, changed)
        with self.assertRaisesRegex(ValueError, "only by the r120/r199/r210/r264/r273/r287 replay"):
            lineage.build(self.source, historical_evidence=evidence)
        with self.assertRaisesRegex(ValueError, "exact original cartridge"):
            lineage.build(source, historical_evidence=evidence)

    def test_ancestry_static_receipt_pin_cannot_be_skipped(self):
        ancestry = lineage.ancestry
        source = (ROOT / "tmp/stage4-menu-exit-invalidation-r287/candidate.gb").read_bytes()
        evidence = {name: (ROOT / path).read_bytes()
                    for name, (path, _) in ancestry.HISTORICAL_INPUTS.items()}
        broken = replace(ancestry.PRE_BRANCH[0], receipt="0" * 64)
        with patch.object(ancestry, "PRE_BRANCH", (broken,) + ancestry.PRE_BRANCH[1:]):
            with self.assertRaisesRegex(ValueError, "generated static receipt differs"):
                ancestry.build(source, evidence)

    def test_stage4_inputs_and_generated_pins_fail_closed(self):
        stage4 = lineage.stage4
        source = (ROOT / "tmp/stage7-skip-invisible-padding-r273/candidate.gb").read_bytes()
        evidence = {name: (ROOT / path).read_bytes()
                    for name, (path, _) in stage4.HISTORICAL_INPUTS.items()}
        with self.assertRaisesRegex(ValueError, "exact retained r273"):
            stage4.build(self.source, evidence)
        for changed in ({}, {**evidence, "unexpected": b""}):
            with self.assertRaisesRegex(ValueError, "exactly the fifteen"):
                stage4.build(source, changed)
        for name in evidence:
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "historical evidence identity differs"):
                    stage4.build(source, {**evidence, name: evidence[name] + b" "})
        for field, error in (("rom", "generated ROM differs"),
                             ("receipt", "generated static receipt differs")):
            broken = replace(stage4.STEPS[0], **{field: "0" * 64})
            with patch.object(stage4, "STEPS", (broken,) + stage4.STEPS[1:]):
                with self.assertRaisesRegex(ValueError, error):
                    stage4.build(source, evidence)
        with patch.object(stage4, "STEPS", ()):
            with self.assertRaisesRegex(ValueError, "did not reproduce exact r287"):
                stage4.build(source, evidence)
        stock = (ROOT / "rom/Penta Dragon (J).gb").read_bytes()
        for changed in (evidence, {**evidence, "unexpected": b""}):
            with self.assertRaisesRegex(ValueError, "exactly the twenty"):
                lineage.build(source, original_rom=stock, historical_evidence=changed)

    def test_stage4_explicit_evidence_never_falls_back_to_disk(self):
        import build_stage4_lazy_departure_r285 as r285
        evidence = {path: (ROOT / path).read_bytes()
                    for path, _ in lineage.stage4.HISTORICAL_INPUTS.values()}
        expected = (r285.verify_corpora(), r285.verify_wram_ownership())
        with patch.object(Path, "read_bytes", side_effect=AssertionError("hidden disk input")):
            self.assertEqual((r285.verify_corpora(evidence), r285.verify_wram_ownership(evidence)), expected)
            with self.assertRaisesRegex(AssertionError, "missing explicit historical input"):
                r285.verify_corpora({})
            with self.assertRaisesRegex(AssertionError, "missing explicit historical input"):
                r285.verify_wram_ownership({})

    def test_stage7_historical_receipts_and_generated_pins_are_required(self):
        stage7 = lineage.stage7
        source = (ROOT / "tmp/stage1-menu-hidden-repair-r264/candidate.gb").read_bytes()
        evidence = {name: (ROOT / path).read_bytes()
                    for name, (path, _) in stage7.HISTORICAL_INPUTS.items()}
        with self.assertRaisesRegex(ValueError, "exact repaired r264"):
            stage7.build(self.source, evidence)
        for changed in ({}, {**evidence, "unexpected": b""}):
            with self.assertRaisesRegex(ValueError, "exactly the two historical static"):
                stage7.build(source, changed)
        for name in evidence:
            with self.assertRaisesRegex(ValueError, "historical evidence identity differs"):
                stage7.build(source, {**evidence, name: evidence[name] + b" "})
        for field, error in (("rom", "generated ROM differs"), ("receipt", "generated receipt differs")):
            broken = replace(stage7.STEPS[0], **{field: "0" * 64})
            with patch.object(stage7, "STEPS", (broken,) + stage7.STEPS[1:]):
                with self.assertRaisesRegex(ValueError, error):
                    stage7.build(source, evidence)
        with patch.object(stage7, "STEPS", ()):
            with self.assertRaisesRegex(ValueError, "did not reproduce exact r273"):
                stage7.build(source, evidence)
        stock = (ROOT / "rom/Penta Dragon (J).gb").read_bytes()
        with self.assertRaisesRegex(ValueError, "exactly the twenty-two"):
            lineage.build(source, original_rom=stock, historical_evidence=evidence)

    def test_stage7_source_checks_are_rerun_without_relabeling_historical_corpora(self):
        stage7 = lineage.stage7
        source = (ROOT / "tmp/stage1-menu-hidden-repair-r264/candidate.gb").read_bytes()
        evidence = {name: (ROOT / path).read_bytes()
                    for name, (path, _) in stage7.HISTORICAL_INPUTS.items()}
        import audit_stage7_dual_plane_hdma_r264 as audit
        for name in ("guard_contract", "require_runtime", "timing_contract"):
            with self.subTest(check=name):
                with patch.object(audit, name, return_value={"unexpected": True}):
                    with self.assertRaisesRegex(ValueError, "source contract differs"):
                        stage7.build(source, evidence)
        with patch.object(Path, "read_bytes", side_effect=AssertionError("hidden intermediate read")):
            _, records = stage7.build(source, evidence)
        first = records[0]
        self.assertEqual(first["generated_receipt_kind"], "construction-only")
        self.assertEqual(len(first["source_contracts_rechecked"]), 11)
        for record in records:
            self.assertFalse(record["historical_corpora_rechecked"])
            self.assertFalse(record["fresh_live_qualification"])
        self.assertEqual(first["historical_evidence_sha256"], {
            "stage7_dual_plane_static": stage7.HISTORICAL_INPUTS["stage7_dual_plane_static"][1]})
        self.assertNotEqual(first["generated_receipt_sha256"],
                            first["historical_evidence_sha256"]["stage7_dual_plane_static"])

    def test_r265_explicit_inputs_preserve_standalone_checks(self):
        import build_stage7_menu_signature_invalidation_r265 as r265
        source = r265.BASE.read_bytes()
        receipt = r265.BASE_RECEIPT.read_bytes()
        control = r265.R264_CONTROL.read_bytes()
        expected = r265.build(source)
        with patch.object(Path, "read_bytes", side_effect=AssertionError("hidden artifact read")):
            self.assertEqual(r265.build(source, base_receipt=receipt, control=control), expected)
            with self.assertRaisesRegex(AssertionError, "static receipt changed"):
                r265.build(source, base_receipt=b"", control=control)
            with self.assertRaisesRegex(AssertionError, "control is missing or changed"):
                r265.build(source, base_receipt=receipt, control=b"")

    def test_stage2_ancestry_cannot_skip_input_output_or_receipt_pins(self):
        stage2 = lineage.stage2
        source = (ROOT / "tmp/stage1-deferred-palette-r210/candidate.gb").read_bytes()
        with self.assertRaisesRegex(ValueError, "exact retained r210"):
            stage2.build(self.source)
        for field, error in (("rom", "generated ROM differs"),
                             ("receipt", "generated static receipt differs")):
            broken = replace(stage2.STEPS[0], **{field: "0" * 64})
            with patch.object(stage2, "STEPS", (broken,) + stage2.STEPS[1:]):
                with self.assertRaisesRegex(ValueError, error):
                    stage2.build(source)
        with patch.object(stage2, "STEPS", ()):
            with self.assertRaisesRegex(ValueError, "did not reproduce exact repaired r264"):
                stage2.build(source)
        with self.assertRaisesRegex(ValueError, "exact original cartridge"):
            lineage.build(source)
        with self.assertRaisesRegex(ValueError, "generates its own static build receipts"):
            lineage.build(source, base_receipt=b"{}")
        stock = (ROOT / "rom/Penta Dragon (J).gb").read_bytes()
        with self.assertRaisesRegex(ValueError, "exactly the twenty-two"):
            lineage.build(source, original_rom=stock)

    def test_r231_in_memory_builder_preserves_exact_model_and_cli_receipt(self):
        import build_oam_xflip_fast_r231 as r231
        source = (ROOT / "tmp/stage1-deferred-palette-r210/candidate.gb").read_bytes()
        expected = (ROOT / "tmp/oam-xflip-fast-r231/candidate.gb").read_bytes()
        expected_receipt = (ROOT / "tmp/oam-xflip-fast-r231/static-receipt.json").read_bytes()
        with patch.object(Path, "read_bytes", side_effect=AssertionError("hidden artifact read")):
            candidate, receipt = r231.build(source)
        self.assertEqual(candidate, expected)
        self.assertEqual((json.dumps(receipt, indent=2) + "\n").encode(), expected_receipt)
        self.assertEqual(receipt["exhaustive_model_cases"], 256 * 256 * 5)
        with self.assertRaisesRegex(SystemExit, "unqualified exact r210 base"):
            r231.build(source[:-1])
        with patch.object(r231, "new_model", return_value=(-1, -1, -1, -1)):
            with self.assertRaisesRegex(SystemExit, "semantic mismatch"):
                r231.build(source)

    def test_phase_ancestry_authenticates_all_traces_and_outputs(self):
        phase = lineage.phase
        source = (ROOT / "tmp/stage1-stale-window-hide-r199/candidate.gb").read_bytes()
        evidence = {name: (ROOT / path).read_bytes()
                    for name, (path, _) in phase.HISTORICAL_INPUTS.items()}
        with self.assertRaisesRegex(ValueError, "exact retained r120 or r199"):
            phase.build(self.source, evidence)
        for changed in ({}, {**evidence, "unexpected": b""}):
            with self.assertRaisesRegex(ValueError, "exactly the six historical"):
                phase.build(source, changed)
        for name in evidence:
            with self.assertRaisesRegex(ValueError, "historical evidence identity differs"):
                phase.build(source, {**evidence, name: evidence[name] + b" "})
        for field, error in (("rom", "generated ROM differs"),
                             ("receipt", "generated static receipt differs")):
            broken = replace(phase.STEPS[0], **{field: "0" * 64})
            with patch.object(phase, "STEPS", (broken,) + phase.STEPS[1:]):
                with self.assertRaisesRegex(ValueError, error):
                    phase.build(source, evidence)
        with patch.object(phase, "STEPS", ()):
            with self.assertRaisesRegex(ValueError, "did not reproduce exact r210"):
                phase.build(source, evidence)
        stock = (ROOT / "rom/Penta Dragon (J).gb").read_bytes()
        with self.assertRaisesRegex(ValueError, "exactly the twenty-eight"):
            lineage.build(source, original_rom=stock, historical_evidence=evidence)

    def test_phase_builders_preserve_standalone_results_and_reject_bad_traces(self):
        import build_stage1_phase_content_key_r208 as r208
        import build_stage1_split_phase_key_r209 as r209
        import build_stage1_deferred_palette_r210 as r210
        traces = {Path(path): (ROOT / path).read_bytes()
                  for path, _ in lineage.phase.HISTORICAL_INPUTS.values()}
        bases = ("stage1-stale-window-hide-r199", "stage1-phase-content-key-r208",
                 "stage1-split-phase-key-r209")
        outputs = ("stage1-phase-content-key-r208", "stage1-split-phase-key-r209",
                   "stage1-deferred-palette-r210")
        for builder, base, output in zip((r208, r209, r210), bases, outputs):
            with self.subTest(builder=builder.__name__):
                source = (ROOT / "tmp" / base / "candidate.gb").read_bytes()
                expected = builder.build(source)
                self.assertEqual(expected[0], (ROOT / "tmp" / output / "candidate.gb").read_bytes())
                self.assertEqual((json.dumps(expected[1], indent=2) + "\n").encode(),
                                 (ROOT / "tmp" / output / "static-receipt.json").read_bytes())
                with patch.object(Path, "read_bytes", side_effect=AssertionError("hidden ROM/trace read")):
                    with patch.object(Path, "open", side_effect=AssertionError("hidden trace open")):
                        options = {"traces": traces} if builder != r210 else {}
                        self.assertEqual(builder.build(source, **options), expected)
                with self.assertRaises(SystemExit):
                    builder.build(source[:-1])
        with self.assertRaisesRegex(SystemExit, "no transition traces"):
            r208.collect_traces(r208.DEFAULT_CORPORA, {})
        with self.assertRaisesRegex(ValueError, "unused explicit transition trace"):
            r208.collect_traces(r208.DEFAULT_CORPORA, {**traces, Path("unexpected/events.tsv"): b""})
        source = (ROOT / "tmp/stage1-stale-window-hide-r199/candidate.gb").read_bytes()
        with patch.object(r208, "assess", return_value={"false_negatives": 1}):
            with self.assertRaisesRegex(SystemExit, "key misses transitions"):
                r208.build(source, traces=traces)
        source = (ROOT / "tmp/stage1-phase-content-key-r208/candidate.gb").read_bytes()
        selected = next(iter(traces))
        lines = traces[selected].decode().splitlines()
        row = lines[1].split("\t")
        row[lines[0].split("\t").index("plane")] = "00"
        lines[1] = "\t".join(row)
        malformed = {**traces, selected: ("\n".join(lines) + "\n").encode()}
        with self.assertRaisesRegex(SystemExit, "invalid transition plane"):
            r209.build(source, traces=malformed)

    def test_transition_assessment_explicit_text_preserves_file_results(self):
        from verify_stage1_transition_key import assess, PRODUCTION_FEATURES, STAGE1_LUT_OFFSET
        source = (ROOT / "tmp/stage1-stale-window-hide-r199/candidate.gb").read_bytes()
        lut = source[STAGE1_LUT_OFFSET:STAGE1_LUT_OFFSET + 256]
        for path, _ in lineage.phase.HISTORICAL_INPUTS.values():
            trace = ROOT / path
            payload = trace.read_text()
            for canonical in (None, lut):
                expected = assess(trace, PRODUCTION_FEATURES, canonical)
                with patch.object(Path, "open", side_effect=AssertionError("hidden trace open")):
                    self.assertEqual(assess(trace, PRODUCTION_FEATURES, canonical,
                                            trace_text=payload), expected)

    def test_early_phase_builders_reproduce_static_receipts_and_timing(self):
        bases = ("source-integration-r120", "stage1-r74-semantic-key-r190",
                 "stage1-live-key-demo-dirty-r194")
        outputs = ("stage1-r74-semantic-key-r190", "stage1-live-key-demo-dirty-r194",
                   "stage1-stale-window-hide-r199")
        for pin, base, output in zip(lineage.phase.EARLY_STEPS, bases, outputs):
            with self.subTest(builder=pin.module):
                builder = importlib.import_module(pin.module)
                source = (ROOT / "tmp" / base / "candidate.gb").read_bytes()
                expected = (ROOT / "tmp" / output / "candidate.gb").read_bytes()
                expected_receipt = (ROOT / "tmp" / output / "static-receipt.json").read_bytes()
                with patch.object(Path, "read_bytes", side_effect=AssertionError("hidden artifact read")):
                    candidate, receipt = builder.build(source)
                self.assertEqual(candidate, expected)
                self.assertEqual((json.dumps(receipt, indent=2) + "\n").encode(), expected_receipt)
                with self.assertRaisesRegex(SystemExit, "unqualified exact"):
                    builder.build(source[:-1])
                if output.endswith("r199"):
                    self.assertEqual(receipt["normal_fallthrough_cycles_before"], 192)
                    self.assertEqual(receipt["normal_fallthrough_cycles_after"], 192)
                    self.assertTrue(receipt["normal_registers_flags_and_memory_preserved"])

    def test_r120_ancestry_rejects_changed_pins_and_missing_evidence(self):
        phase = lineage.phase
        source = (ROOT / "tmp/source-integration-r120/candidate.gb").read_bytes()
        evidence = {name: (ROOT / path).read_bytes()
                    for name, (path, _) in phase.HISTORICAL_INPUTS.items()}
        for field, error in (("rom", "generated ROM differs"),
                             ("receipt", "generated static receipt differs")):
            broken = replace(phase.EARLY_STEPS[0], **{field: "0" * 64})
            with patch.object(phase, "EARLY_STEPS", (broken,) + phase.EARLY_STEPS[1:]):
                with self.assertRaisesRegex(ValueError, error):
                    phase.build(source, evidence)
        with patch.object(phase, "STEPS", ()):
            with self.assertRaisesRegex(ValueError, "did not reproduce exact r210"):
                phase.build(source, evidence)
        with self.assertRaisesRegex(ValueError, "exactly the six historical"):
            phase.build(source, {})
        with self.assertRaisesRegex(ValueError, "exact original cartridge"):
            lineage.build(source)
        stock = (ROOT / "rom/Penta Dragon (J).gb").read_bytes()
        with self.assertRaisesRegex(ValueError, "exactly the twenty-eight"):
            lineage.build(source, original_rom=stock, historical_evidence=evidence)

    def test_historical_bundle_paths_are_explicit_and_unambiguous(self):
        paths = lineage.historical_paths('{"stage4_live": "tmp/capture.tsv"}',
                                         {"room01_capture": Path("input.bin")})
        self.assertEqual(paths, {"stage4_live": lineage.ROOT / "tmp/capture.tsv",
                                 "room01_capture": Path("input.bin")})
        self.assertEqual(lineage.historical_paths('{"stage4_live": "/input/capture.tsv"}', {}),
                         {"stage4_live": Path("/input/capture.tsv")})
        for payload, explicit in (
            ('[]', {}), ('{"unknown": "x"}', {}),
            ('{"stage4_live": null}', {}), ('{"stage4_live": ""}', {}),
            ('{"stage4_live": "a", "stage4_live": "b"}', {}),
            ('{"stage4_live": "a"}', {"stage4_live": Path("b")}),
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    lineage.historical_paths(payload, explicit)

    def test_runtime_layout_is_source_defined_without_rom_access(self):
        import build_stage1_scene0b_exact_runtime_delta_r335 as delta
        import build_stage1_hazard_terminal_silhouette_r343 as art
        with patch.object(Path, "read_bytes", side_effect=AssertionError("unexpected ROM read")):
            regions = delta.selected_regions()
            cave = art._r342_cave_layout()
            selected = delta.selected(self.source)
        self.assertEqual(len(regions), len(selected))
        for (label, offset, destination, width), selected_region in zip(regions, selected):
            self.assertEqual(selected_region, (label, destination, self.source[offset:offset + width]))
            self.assertEqual(len(selected_region[2]), width)
        self.assertEqual(cave[2], art.r342.CAVE_ADDR + cave[1])

    def test_missing_generated_reference_rejects_before_import(self):
        source = (ROOT / "tmp/stage1-hazard-terminal-silhouette-r343/candidate.gb").read_bytes()
        step = lineage.prefix.Step("must_not_import", "0" * 64,
                                   reference_sha256="1" * 64)
        with patch.object(lineage.prefix, "STEPS", (step,)):
            with self.assertRaisesRegex(ValueError, "missing or changed generated reference"):
                lineage.prefix.build(source)

    def test_explicit_merge_references_preserve_bytes_and_reject_wrong_hash(self):
        for name, reference_path in (
            ("build_combined_scanner_copy_r380", "deferred-commit-guard-r374"),
            ("build_combined_dma_compile_r434", "stage5-private-pointer-r424"),
        ):
            with self.subTest(builder=name):
                builder = importlib.import_module(name)
                source = builder.BASE.read_bytes()
                reference = (ROOT / "tmp" / reference_path / "candidate.gb").read_bytes()
                self.assertEqual(builder.build(source),
                                 builder.build(source, reference=reference))
                damaged = bytearray(reference)
                damaged[0x14F] ^= 1
                with self.assertRaises(ValueError):
                    builder.build(source, reference=bytes(damaged))

    def test_step_output_and_receipt_drift_reject(self):
        source_sha = hashlib.sha256(self.source).hexdigest()
        for name, expected, output, error in (
            ("bad-size", source_sha, self.source[:-1], "size changed"),
            ("bad-hash", "0" * 64, self.source, "output hash differs"),
            ("bad-base-receipt", source_sha,
             (self.source, {"base_sha256": "0" * 64}), "receipt base_sha256"),
            ("bad-output-receipt", source_sha,
             (self.source, {"candidate_sha256": "0" * 64}), "receipt candidate_sha256"),
        ):
            with self.subTest(name=name):
                steps = ((name, expected, lambda source: output),)
                with patch.object(lineage, "STEPS", steps):
                    with self.assertRaisesRegex(ValueError, error):
                        lineage.build(self.source)

    def test_reload_records_actual_input_without_global_state_changes(self):
        reload = lineage.reload
        constants = (reload.CAVE_TEST, reload.CAVE_SET, reload.CAVE_END)
        base, _ = lineage.dma.build(self.source, isr_pretest_on=True)
        result, receipt = reload.build(
            base, reload.CAVE_TEST_F, reload.CAVE_SET_F,
            base_sha=hashlib.sha256(base).hexdigest(),
        )
        self.assertEqual(receipt["base_sha256"], lineage.STEPS[0][1])
        self.assertEqual(receipt["candidate_sha256"], lineage.STEPS[1][1])
        self.assertEqual(hashlib.sha256(result).hexdigest(), lineage.STEPS[1][1])
        self.assertEqual((reload.CAVE_TEST, reload.CAVE_SET, reload.CAVE_END), constants)
        # Alternate back to the default layout in the same interpreter.
        default_base, _ = lineage.dma.build(self.source)
        default_result, default_receipt = reload.build(default_base)
        self.assertEqual(default_receipt["base_sha256"], reload.BASE_SHA)
        self.assertEqual(default_result, reload.build(default_base)[0])
        self.assertEqual((reload.CAVE_TEST, reload.CAVE_SET, reload.CAVE_END), constants)

    def test_helper_and_recovery_reject_changed_preimages(self):
        wide = lineage.wide
        source = bytearray(b"\xff" * (32 * 0x4000))
        start = wide.off(wide.BANK, wide.ORG)
        source[start:start + len(wide.OLD)] = wide.OLD
        for offset in (start, start + len(wide.OLD)):
            damaged = bytearray(source)
            damaged[offset] ^= 1
            with self.assertRaises(AssertionError):
                wide.build(bytes(damaged), class_gate=True, ei_gap=True, fused=True)
        with self.assertRaisesRegex(AssertionError, "reviewed d82"):
            lineage.recovery.build(bytes(source))


if __name__ == "__main__":
    unittest.main()
