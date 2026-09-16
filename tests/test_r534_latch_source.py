"""Source-only latch/row construction must preserve the historical audit path."""
from contextlib import ExitStack
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
import r534_stage1_latch_source as latch


class LatchSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = ROOT / "tmp/r534-room-source-current510/intermediate-r314.gb"
        if not fixture.is_file():
            raise unittest.SkipTest("exact room-source r314 fixture is unavailable")
        cls.source = fixture.read_bytes()
        cls.r317, _ = latch.cold.construct(cls.source)
        cls.r318, _ = latch.row.construct(cls.r317)
        cls.cases = ((latch.relocation, cls.source), (latch.cold, cls.source),
                     (latch.row, cls.r317), (latch.effective, cls.r318))

    def test_no_historical_builds_reads_or_observation_claims(self):
        with ExitStack() as stack:
            for builder, _ in self.cases:
                for method in ("build", "validate_preimages"):
                    stack.enter_context(patch.object(builder, method, side_effect=AssertionError("historical audit")))
            stack.enter_context(patch.object(Path, "read_bytes", side_effect=AssertionError("artifact read")))
            result, receipt = latch.construct(self.source)
            self.assertEqual((result, receipt), latch.construct(self.source))
        self.assertEqual(latch.digest(result), latch.OUTPUT_SHA256)
        self.assertEqual(len(receipt["steps"]), 3)
        self.assertEqual(len(receipt["components"]), 4)
        for key in ("promotable", "historical_evidence_consumed", "fresh_live_qualification"):
            self.assertIs(receipt[key], False)
        for component in receipt["components"].values():
            self.assertEqual(component["status"], "construction-only")
            self.assertIs(component["emulator_invoked"], False)
        text = json.dumps(receipt)
        for claim in ("build_receipt_sha256", "executable-code audit found", "SC owner found", "B=$08"):
            self.assertNotIn(claim, text)
        self.assertIn("Pocket", text)
        self.assertIn("required_live_gates", text)

    def test_historical_receipts_remain_required_and_identical(self):
        for builder, source in self.cases:
            with self.subTest(builder=builder.__name__):
                with self.assertRaisesRegex(AssertionError, "receipt identity"):
                    builder.build(source, b"")
                actual, receipt = builder.build(source, builder.BASE_RECEIPT.read_bytes())
                self.assertEqual(latch.digest(actual), builder.EXPECTED_CANDIDATE_SHA256)
                self.assertEqual(latch.serialize_receipt(receipt), builder.DEFAULT_RECEIPT.read_bytes())

    def test_input_and_output_pins_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "exact r314"):
            latch.construct(self.source[:-1])
        for builder, source in self.cases:
            with self.subTest(builder=builder.__name__), self.assertRaises(AssertionError):
                builder.construct(source[:-1])
            with self.subTest(builder=builder.__name__), patch.object(builder, "EXPECTED_CANDIDATE_SHA256", "0" * 64):
                with self.assertRaisesRegex(AssertionError, "candidate identity drift|module identity changed"):
                    builder.construct(source)
        for index, pin in enumerate(latch.EARLY_STEPS[:3]):
            altered = list(latch.EARLY_STEPS)
            altered[index] = replace(pin, output_sha256="0" * 64)
            with self.subTest(index=index), patch.object(latch, "EARLY_STEPS", tuple(altered)):
                with self.assertRaisesRegex(ValueError, "generated ROM differs"):
                    latch.construct(self.source)
        with patch.object(latch, "RELOCATION_SHA256", "0" * 64):
            with self.assertRaisesRegex(ValueError, "generated ROM differs"):
                latch.construct(self.source)

    def test_source_contract_pins_fail_closed(self):
        for revision in latch.SOURCE_CONTRACT_SHA256:
            changed = {**latch.SOURCE_CONTRACT_SHA256, revision: "0" * 64}
            with self.subTest(revision=revision), patch.object(latch, "SOURCE_CONTRACT_SHA256", changed):
                with self.assertRaisesRegex(ValueError, "contract receipt differs"):
                    latch.construct(self.source)
        with patch.object(latch, "SOURCE_CONTRACT_SHA256", {}):
            with self.assertRaisesRegex(ValueError, "pin inventory differs"):
                latch.construct(self.source)
        for builder, method in ((latch.relocation, "collision_contract"), (latch.cold, "dispatcher_contract"),
                                (latch.row, "exhaustive_contract"), (latch.effective, "exhaustive_contract")):
            with self.subTest(builder=builder.__name__), patch.object(builder, method, return_value={}):
                with self.assertRaisesRegex(ValueError, "contract receipt differs"):
                    latch.construct(self.source)

    def test_source_preimages_fail_closed(self):
        for builder, source, constant, message in (
            (latch.relocation, self.source, "STOCK_READER", "native indirect selector reader drift"),
            (latch.cold, self.source, "DISPATCH_PREIMAGE", "dispatcher/pad preimage drift"),
            (latch.row, self.r317, "OLD_ROW_PREFIX", "row prefix preimage drift"),
            (latch.effective, self.r318, "OLD_TRAMPOLINE", "full trampoline preimage drifted"),
        ):
            with self.subTest(builder=builder.__name__), patch.object(builder, constant, bytes(len(getattr(builder, constant)))):
                with self.assertRaisesRegex(AssertionError, message):
                    builder.construct(source)

    def test_factory_to_r319_double_build_without_historical_input_reads(self):
        program = r'''
import json,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve()
factory=(root/'tmp/r534-palette-source-current511/build-1/factory.gb').read_bytes()
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
first=None
for _ in range(2):
    r287,prefix_receipt=prefix.build(factory)
    r314,room_receipt=room.construct(r287)
    result,receipt=latch.construct(r314)
    item=(result,prefix_receipt,room_receipt,receipt)
    if first is not None: assert item==first
    first=item
    assert latch.digest(result)==latch.OUTPUT_SHA256
print(json.dumps({'candidate_sha256':latch.digest(first[0]),'historical_inputs_read':0}))
'''
        run = subprocess.run([sys.executable, "-I", "-B", "-c", program, str(ROOT),
                              str(Path(yaml.__file__).resolve().parent.parent)],
                             cwd=ROOT, capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(json.loads(run.stdout)["historical_inputs_read"], 0)


if __name__ == "__main__":
    unittest.main()
