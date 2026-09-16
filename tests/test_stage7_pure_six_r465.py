import hashlib
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))

import compose_stage7_pure_six_r465 as candidate


class Stage7PureSix(unittest.TestCase):
    def test_exact_copy_sequence_and_timing_bound(self):
        fast, evidence = candidate.emit_fast_copier(include_prefix=True)
        self.assertEqual(
            candidate.emitter.model_new(fast),
            candidate.emitter.model_old(),
        )
        self.assertEqual(evidence["group_count"], 96)
        self.assertEqual(evidence["cells"], 576)
        self.assertEqual(evidence["maximum_critical_cycles"], 41)
        self.assertLessEqual(evidence["maximum_critical_cycles"], 41.75)
        self.assertGreater(evidence["groups_with_source_page_crossing"], 0)

    def test_exhaustive_dispatcher_routes(self):
        old, new, evidence = candidate.code_pair()
        dispatcher_start = evidence["old_size"]
        dispatcher_end = evidence["fast_address"] - candidate.emitter.ORG
        dispatcher = new[dispatcher_start:dispatcher_end]
        for ffba in range(256):
            for ff01 in range(256):
                for lcdc in (0x00, 0x80):
                    route, rows = candidate.execute_dispatcher(
                        dispatcher,
                        address=evidence["dispatcher_address"],
                        fast_address=evidence["fast_address"],
                        normal_return=evidence["normal_return"],
                        ffba=ffba,
                        ff01=ff01,
                        lcdc=lcdc,
                    )
                    expected_fast = ffba == 6 and not (ff01 & 1) and bool(lcdc & 0x80)
                    self.assertEqual(route == "fast", expected_fast)
                    if route == "normal":
                        self.assertEqual(rows, 24 if ffba == 0 or ff01 & 1 else 0)
        self.assertEqual(old[:evidence["gate_index"]], new[:evidence["gate_index"]])

    def test_candidate_scope_and_preimages(self):
        source = candidate.BASE.read_bytes()
        result, evidence = candidate.build(source)
        start = candidate.emitter.off(candidate.emitter.BANK, candidate.emitter.ORG)
        allowed = set(range(start, start + evidence["new_size"])) | {0x14D, 0x14E, 0x14F}
        self.assertLessEqual(
            {index for index, pair in enumerate(zip(source, result)) if pair[0] != pair[1]},
            allowed,
        )
        self.assertEqual(len(result), len(source))
        changed = bytearray(source)
        changed[start + evidence["gate_index"]] ^= 1
        with self.assertRaises(ValueError):
            candidate.build(bytes(changed))
        self.assertEqual(
            hashlib.sha256(source).hexdigest(),
            candidate.BASE_SHA256,
        )


if __name__ == "__main__":
    unittest.main()
