"""#27 narrow graphics-owner regression; full replay failure stays visible."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
import build_arena_graphics_owner_trial as trial
from verify_pickup_class_palettes import serialized_state


class GraphicsOwner(unittest.TestCase):
    def test_changes_only_six_read_operands_and_checksum(self):
        path = ROOT/'tmp/arena-sound-alias-trial-01/candidate.gb'
        if not path.exists():
            self.skipTest('local parent unavailable')
        parent = path.read_bytes()
        result = trial.build(parent)
        allowed = {0x14E, 0x14F}
        for bank in (13, 16):
            for addr, _ in trial.SITES:
                pos = bank*16384+addr-16384
                allowed.update((pos+1, pos+2))
                self.assertEqual(result[pos:pos+3], bytes.fromhex('FA0DDF'))
        changed = {i for i,(a,b) in enumerate(zip(parent,result)) if a != b}
        self.assertTrue(changed <= allowed)
        self.assertEqual(len(parent), len(result))
        with self.assertRaises(ValueError):
            trial.build(result)

    def test_live_owner_and_retained_failure(self):
        folder = ROOT/'tmp/arena-graphics-owner-shalamar-phase721-01'
        if not (folder/'verification.json').exists():
            self.skipTest('local replay unavailable')
        rom = (ROOT/'tmp/arena-graphics-owner-trial-01/candidate.gb').read_bytes()
        self.assertEqual(hashlib.sha256(rom).hexdigest(),
                         '35a8d40bc9ed8cf3d967d0c01df0674bcf119a0ec0364ef1bcb60493a9448af7')
        aliases = 0
        for frame in range(1, 1081):
            raw = serialized_state(folder/f'frame-{frame:04d}.ss0')
            self.assertEqual(int.from_bytes(raw[4:8],'little'), zlib.crc32(rom)&0xffffffff)
            for offset in (0x5EBB,0x5FA6,0x5F80):
                self.assertEqual(raw[offset:offset+3], bytes.fromhex('FA0DDF'))
            if raw[0x5c80] == 11 and raw[0x3b7] == 12:
                aliases += 1
                self.assertEqual(raw[0x630d],12)
                self.assertEqual(raw[0x4a00:0x4b00],bytes([0,0]+[4]*253+[0]))
        self.assertEqual(aliases,156)
        self.assertEqual(raw[0x3e4],0)  # final gameplay, not low-health menu
        verdict = json.loads((folder/'verification.json').read_text())
        self.assertEqual([c['status'] for c in verdict['cycles']],['PASS','FAIL','PASS'])
        self.assertEqual(verdict['cycles'][1]['map_readiness']['failures'],
                         [{'frame':597,'mismatch_count':24}])

    def test_same_prefix_and_visible_change_after_alias(self):
        new = ROOT/'tmp/arena-graphics-owner-shalamar-phase721-01'
        old = ROOT/'tmp/arena-sound-alias-shalamar-phase721-01'
        if not (new/'frame-1080.png').exists() or not (old/'frame-1080.png').exists():
            self.skipTest('local paired captures unavailable')
        changes = [f for f in range(1,1081)
                   if (new/f'frame-{f:04d}.png').read_bytes() != (old/f'frame-{f:04d}.png').read_bytes()]
        self.assertEqual(changes,list(range(929,1081)))


if __name__ == '__main__':
    unittest.main()
