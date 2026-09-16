from pathlib import Path
import hashlib
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))
import build_stage_card_private_trial_r535 as trial
import build_title_tile_retire_trial_r535 as title


class StageCardPrivateTrialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = title.build((ROOT / "tmp/stage4-cache-key-r534/candidate.gb").read_bytes())

    def test_source_identity_checksum_and_determinism(self):
        self.assertEqual(hashlib.sha256(self.source).hexdigest(), trial.BASE_SHA)
        rom = trial.build(self.source)
        self.assertEqual(rom, trial.build(self.source))
        self.assertEqual(rom[0x14E:0x150], ((sum(rom[:0x14E])+sum(rom[0x150:]))&65535).to_bytes(2,"big"))

    def test_shared_dispatch_is_byte_identical_to_parent(self):
        rom = trial.build(self.source)
        self.assertEqual(rom[31*0x4000:], self.source[31*0x4000:])
        self.assertEqual(rom[trial.HOOK:trial.HOOK+5], bytes.fromhex("3E 14 CD 47 08"))
        self.assertEqual(rom[trial.CAVE:trial.CAVE+69], trial.shared.payloads()[1])

    def test_neighbor_and_all_unowned_bytes_are_preserved(self):
        rom = trial.build(self.source)
        owned = set(range(trial.HOOK,trial.HOOK+5)) | set(range(trial.CAVE,trial.CAVE+69)) | {0x14E,0x14F}
        self.assertLessEqual({i for i,(x,y) in enumerate(zip(self.source,rom,strict=True)) if x!=y}, owned)
        self.assertEqual(rom[trial.CAVE+69:trial.CAVE+0x60], self.source[trial.CAVE+69:trial.CAVE+0x60])

    def test_unknown_source_and_occupied_cave_fail_closed(self):
        for offset in (0x14F, trial.HOOK, trial.CAVE, trial.CAVE+0x55):
            changed = bytearray(self.source)
            changed[offset] ^= 1
            with self.assertRaises(ValueError):
                trial.build(changed)


if __name__ == "__main__":
    unittest.main()
