"""Source-only r534 integration, without retained ROM or observation inputs."""
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
import build_r534_source_candidate as source


class SourceCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = ROOT / "tmp/r534-admission-source-current514/intermediate-r336.gb"
        if not fixture.is_file():
            raise unittest.SkipTest("exact source-only r336 fixture is unavailable")
        cls.r336 = fixture.read_bytes()
        cls.original = (ROOT / "rom/Penta Dragon (J).gb").read_bytes()
        cls.factory = (ROOT / "tmp/r534-palette-source-current515/build-1/factory.gb").read_bytes()
        cls.r341, _ = source.caps.construct(cls.r336)
        cls.r342, _ = source.resume.construct(cls.r341)

    def test_hazards_do_not_read_evidence_or_call_audit_builders(self):
        with ExitStack() as stack:
            for _, builder, _, _ in source.HAZARD_COMPONENTS:
                stack.enter_context(patch.object(builder, "build", side_effect=AssertionError("historical build")))
            stack.enter_context(patch.object(Path, "read_bytes", side_effect=AssertionError("artifact read")))
            result, receipt = source.construct_hazards(self.r336, self.original)
            self.assertEqual((result, receipt), source.construct_hazards(self.r336, self.original))
        self.assertEqual(source.digest(result), source.continuation.prefix.BASE_SHA256)
        for component in receipt["components"].values():
            self.assertEqual(component["status"], "construction-only")
            for key in ("promotable", "emulator_invoked", "historical_evidence_consumed", "fresh_live_qualification"):
                self.assertIs(component[key], False)

    def test_historical_hazard_receipts_stay_identical_and_required(self):
        current = self.r336
        for revision, builder, expected, _ in source.HAZARD_COMPONENTS:
            options = {"stock": self.original} if revision == "r343" else {}
            with self.subTest(revision=revision), self.assertRaisesRegex(AssertionError, "receipt targets another candidate"):
                builder.build(current, b"{}", **options)
            current, receipt = builder.build(current, builder.BASE_RECEIPT.read_bytes(), **options)
            self.assertEqual(source.digest(current), expected)
            self.assertEqual(source.serialize_receipt(receipt), builder.RECEIPT.read_bytes())

    def test_hazard_inputs_and_component_pins_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "exact r336"):
            source.construct_hazards(self.r336[:-1], self.original)
        with self.assertRaisesRegex(ValueError, "exact original"):
            source.construct_hazards(self.r336, self.original[:-1])
        with self.assertRaises(TypeError):
            source.silhouette.construct(self.r342)
        for index, item in enumerate(source.HAZARD_COMPONENTS):
            for field, message in ((2, "generated ROM differs"), (3, "contract receipt differs")):
                altered = list(source.HAZARD_COMPONENTS)
                changed = list(item)
                changed[field] = "0" * 64
                altered[index] = tuple(changed)
                with self.subTest(index=index, field=field), patch.object(source, "HAZARD_COMPONENTS", tuple(altered)):
                    with self.assertRaisesRegex(ValueError, message):
                        source.construct_hazards(self.r336, self.original)
        with patch.object(source, "HAZARD_COMPONENTS", ()):
            with self.assertRaisesRegex(ValueError, "pin inventory differs"):
                source.construct_hazards(self.r336, self.original)

    def test_source_configuration_caves_and_art_remain_checked(self):
        with patch.object(source.caps, "TERMINAL_TILES", frozenset()):
            with self.assertRaisesRegex(AssertionError, "YAML contract changed"):
                source.caps.construct(self.r336)
        with patch.object(source.caps, "R336_ENTRY_TAIL", bytes(len(source.caps.R336_ENTRY_TAIL))):
            with self.assertRaisesRegex(AssertionError, "entry tail preimage changed"):
                source.caps.construct(self.r336)
        with patch.object(source.resume, "PATCH_HELPER_ADDR", source.resume.CAVE_ADDR):
            with self.assertRaisesRegex(AssertionError, "overlaps terminal helper"):
                source.resume.construct(self.r341)
        with patch.object(source.silhouette, "compile_stage1_hazard_terminal_variants", return_value={}):
            with self.assertRaisesRegex(AssertionError, "compiler emitted another tile set"):
                source.silhouette.construct(self.r342, stock=self.original)

    def test_join_requires_correct_input_output_and_no_historical_evidence(self):
        with self.assertRaisesRegex(ValueError, "exact original"):
            source.build(self.factory, self.original[:-1])
        with self.assertRaises(ValueError):
            source.build(self.factory[:-1], self.original)
        with patch.object(source, "construct_hazards", return_value=(self.r342, {})):
            with self.assertRaisesRegex(ValueError, "continuation input"):
                source.build(self.factory, self.original)
        bogus = {"historical_evidence": {"unexpected": {}}, "component_builds": []}
        with patch.object(source.continuation, "build", return_value=(b"", bogus)):
            with self.assertRaisesRegex(ValueError, "unexpectedly consumed historical evidence"):
                source.build(self.factory, self.original)
        bogus = {"historical_evidence": {}, "component_builds": [], "base_sha256": "0" * 64}
        with patch.object(source.continuation, "build", return_value=(b"", bogus)):
            with self.assertRaisesRegex(ValueError, "did not reproduce exact r534"):
                source.build(self.factory, self.original)

    def test_isolated_full_double_build_with_only_factory_and_original_inputs(self):
        program = r'''
import json,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve()
factory=(root/'tmp/r534-palette-source-current515/build-1/factory.gb').read_bytes()
original=(root/'rom/Penta Dragon (J).gb').read_bytes()
sys.path[:0]=[str(root/'scripts/diagnostics'),str(root/'scripts'),sys.argv[2]]
def audit(event,args):
    if event=='open' and isinstance(args[0],(str,bytes)):
        raw=args[0].decode() if isinstance(args[0],bytes) else args[0]
        path=(root/raw).resolve()
        if path.is_relative_to(root/'tmp') or path.suffix.lower() in ('.gb','.gbc','.ss0','.ss1'):
            raise AssertionError(f'undeclared artifact read: {path}')
sys.addaudithook(audit)
import build_r534_source_candidate as source
first=None
for _ in range(2):
    result,receipt=source.build(factory,original)
    item=(result,receipt)
    if first is not None: assert item==first
    first=item
    assert source.digest(result)==source.continuation.CANDIDATE_SHA256
    assert receipt['construction_steps']==45 and len(receipt['continuation_steps'])==60
    assert receipt['total_steps']==105 and not receipt['historical_evidence_consumed']
print(json.dumps({'candidate_sha256':source.digest(first[0]),'historical_inputs_read':0,'steps':105}))
'''
        run = subprocess.run([sys.executable, "-I", "-B", "-c", program, str(ROOT),
                              str(Path(yaml.__file__).resolve().parent.parent)],
                             cwd=ROOT, capture_output=True, text=True, timeout=180)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(result["historical_inputs_read"], 0)
        self.assertEqual(result["steps"], 105)


if __name__ == "__main__":
    unittest.main()
