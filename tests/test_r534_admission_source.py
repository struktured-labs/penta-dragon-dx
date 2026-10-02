"""Atomic/admission construction must not impersonate historical observations."""
from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts/diagnostics"), str(ROOT / "scripts")]
import r534_stage1_admission_source as admission


class AdmissionSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = ROOT / "tmp/r534-latch-source-current512/intermediate-r319.gb"
        if not fixture.is_file():
            raise unittest.SkipTest("exact source-only r319 fixture is unavailable")
        cls.source = fixture.read_bytes()
        cls.r320, _ = admission.atomic.construct(cls.source)

    def test_no_audit_calls_artifact_reads_or_observation_claims(self):
        with ExitStack() as stack:
            for _, builder, _, _ in admission.COMPONENTS:
                stack.enter_context(patch.object(builder, "build", side_effect=AssertionError("historical build")))
            for builder in (admission.atomic, admission.return_route):
                stack.enter_context(patch.object(builder, "validate_preimages", side_effect=AssertionError("receipt audit")))
            stack.enter_context(patch.object(admission.runtime, "_build_selected", side_effect=AssertionError("receipt audit")))
            stack.enter_context(patch.object(Path, "read_bytes", side_effect=AssertionError("artifact read")))
            result, receipt = admission.construct(self.source)
            self.assertEqual((result, receipt), admission.construct(self.source))
        self.assertEqual(admission.digest(result), admission.OUTPUT_SHA256)
        self.assertEqual(len(receipt["steps"]), 2)
        self.assertEqual(len(receipt["components"]), 7)
        for key in ("promotable", "historical_evidence_consumed", "fresh_live_qualification"):
            self.assertIs(receipt[key], False)
        for component in receipt["components"].values():
            self.assertEqual(component["status"], "construction-only")
            self.assertIs(component["emulator_invoked"], False)
        encoded = json.dumps(receipt)
        for claim in ("authenticated_da00_delta", "other_DA00_DA5C_differences", "bad_frame",
                      "reviewed_terrain_tile_differences", "build_receipt_sha256", '"receipt_sha256"',
                      "known-good live control flow"):
            self.assertNotIn(claim, encoded)

    def test_historical_builds_retain_exact_receipts(self):
        base_receipt = admission.atomic.BASE_RECEIPT.read_bytes()
        r320, metadata = admission.atomic.build(self.source, base_receipt)
        r320_receipt = admission.serialize_receipt(metadata)
        self.assertEqual(r320_receipt, admission.atomic.DEFAULT_RECEIPT.read_bytes())
        for revision, builder, rom_sha, _ in admission.COMPONENTS:
            source, receipt_bytes = (self.source, base_receipt) if revision == "r320" else (r320, r320_receipt)
            with self.subTest(revision=revision):
                with self.assertRaisesRegex(AssertionError, "receipt identity changed"):
                    builder.build(source, b"")
                result, receipt = builder.build(source, receipt_bytes)
                path = getattr(builder, "DEFAULT_RECEIPT", None) or builder.RECEIPT
                self.assertEqual(admission.digest(result), rom_sha)
                self.assertEqual(admission.serialize_receipt(receipt), path.read_bytes())

    def test_component_and_final_pins_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "exact r319"):
            admission.construct(self.source[:-1])
        for index, (revision, builder, rom_sha, receipt_sha) in enumerate(admission.COMPONENTS):
            for field, message in ((2, "generated ROM differs"), (3, "contract receipt differs")):
                altered = list(admission.COMPONENTS)
                item = list(altered[index])
                item[field] = "0" * 64
                altered[index] = tuple(item)
                with self.subTest(revision=revision, field=field), patch.object(admission, "COMPONENTS", tuple(altered)):
                    with self.assertRaisesRegex(ValueError, message):
                        admission.construct(self.source)
        with patch.object(admission, "COMPONENTS", admission.COMPONENTS[:-1]):
            with self.assertRaisesRegex(ValueError, "pin inventory differs"):
                admission.construct(self.source)
        with patch.object(admission, "OUTPUT_SHA256", "0" * 64):
            with self.assertRaisesRegex(ValueError, "final ROM pin differs"):
                admission.construct(self.source)

    def test_preimages_payload_and_model_checks_remain_live(self):
        with patch.object(admission.atomic, "OLD_PRIMARY", bytes(len(admission.atomic.OLD_PRIMARY))):
            with self.assertRaisesRegex(AssertionError, "publisher preimage changed"):
                admission.atomic.construct(self.source)
        with patch.object(admission.phase.r315, "ART_PAYLOAD_SHA256", "0" * 64):
            with self.assertRaisesRegex(AssertionError, "canonical signed art source identity changed"):
                admission.phase.construct(self.r320)
        with patch.object(admission.menu, "MENU_INVALIDATION", bytes(len(admission.menu.MENU_INVALIDATION))):
            with self.assertRaisesRegex(AssertionError, "menu invalidation preimage changed"):
                admission.menu.construct(self.r320)
        with patch.object(admission.atomic, "mutation_contract", return_value={}):
            with self.assertRaisesRegex(ValueError, "contract receipt differs"):
                admission.construct(self.source)
        with patch.object(admission.delta, "selected", return_value=[("empty", 0xDA16, b"")]):
            with self.assertRaisesRegex(AssertionError, "bad region empty"):
                admission.delta.construct(self.r320)

    def test_selected_region_build_never_rebinds_module_global(self):
        original_emit = admission.runtime._emit
        sentinel = object()
        def checked_emit(*args):
            self.assertIs(admission.runtime.regions, sentinel)
            return original_emit(*args)
        with patch.object(admission.runtime, "regions", sentinel), \
             patch.object(admission.runtime, "_emit", side_effect=checked_emit):
            first, _ = admission.delta.construct(self.r320)
            second, _ = admission.delta.build(self.r320, admission.return_route.BASE_RECEIPT.read_bytes())
        self.assertEqual(first, second)

    def test_factory_to_r336_double_build_without_historical_inputs(self):
        program = r'''
import json,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve()
factory=(root/'tmp/r534-palette-source-current513/build-1/factory.gb').read_bytes()
sys.path[:0]=[str(root/'scripts/diagnostics'),str(root/'scripts'),sys.argv[2]]
def audit(event,args):
    if event=='open' and isinstance(args[0],(str,bytes)):
        raw=args[0].decode() if isinstance(args[0],bytes) else args[0]
        path=(root/raw).resolve()
        if path.is_relative_to(root/'tmp') or path.suffix.lower() in ('.gb','.gbc','.ss0','.ss1'):
            raise AssertionError(f'undeclared artifact read: {path}')
sys.addaudithook(audit)
import build_r534_source_prefix as prefix
import r534_stage1_room_source as room
import r534_stage1_latch_source as latch
import r534_stage1_admission_source as admission
first=None
for _ in range(2):
    r287,p=prefix.build(factory)
    r314,r=room.construct(r287)
    r319,l=latch.construct(r314)
    result,a=admission.construct(r319)
    item=(result,p,r,l,a)
    if first is not None: assert item==first
    first=item
    assert admission.digest(result)==admission.OUTPUT_SHA256
print(json.dumps({'candidate_sha256':admission.digest(first[0]),'historical_inputs_read':0}))
'''
        run = subprocess.run([sys.executable, "-I", "-B", "-c", program, str(ROOT),
                              str(Path(yaml.__file__).resolve().parent.parent)],
                             cwd=ROOT, capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(json.loads(run.stdout)["historical_inputs_read"], 0)


if __name__ == "__main__":
    unittest.main()
