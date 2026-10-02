"""#26 executable routing truth table; emulator validation is separate."""
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
import build_secret_sound_alias_trial as trial


def route(code, stage, raw, canonical):
    pc, a, zero = 0, 0, False
    for _ in range(24):
        op = code[pc]
        if op == 0xf0:
            a = {0xba: stage, 0xb7: canonical}[code[pc+1]]; pc += 2
        elif op == 0xfa:
            assert code[pc+1:pc+3] == bytes.fromhex('80d8')
            a = raw; pc += 3
        elif op == 0xfe:
            zero = a == code[pc+1]; pc += 2
        elif op in (0x20, 0x28):
            delta = code[pc+1]
            if delta >= 128: delta -= 256
            pc += 2
            if zero == (op == 0x28): pc += delta
        elif op == 0x3e:
            assert code[pc:pc+5] == bytes.fromhex('3e24cd4708')
            return 'secret'
        elif op == 0x11:
            assert code[pc:pc+8] == bytes.fromhex('11a0c10e41c3856c')
            return 'native'
        else:
            raise AssertionError(f'unexpected opcode {op:02x}')
    raise AssertionError('gate did not terminate')


class SecretSoundAlias(unittest.TestCase):
    def test_lowhealth_exit_pair(self):
        from verify_pickup_class_palettes import serialized_state, PICKUPS
        import json
        import zlib
        policy = [0]*256
        for item in PICKUPS:
            for tile in item.tiles: policy[tile] = item.palette
        for name, pin, counts in (
                ('secret-sound-alias-lowhealth-exit-01',
                 '877ed7510cd59d79117d160f70493cf4ecff0b1ca822697a3834d119de104f7f', [0]*10),
                ('secret-sound-alias-parent-lowhealth-exit-01', trial.PARENT, [0,0]+[16]*8)):
            base = ROOT/'tmp'/name
            if not (base/'receipt.json').exists(): self.skipTest('local exit evidence unavailable')
            receipt = json.loads((base/'receipt.json').read_text())
            self.assertEqual(receipt['status'], 0)
            rom = (base/'candidate.gb').read_bytes()
            self.assertEqual(hashlib.sha256(rom).hexdigest(), pin)
            observed = []
            for frame in [1]+list(range(10, 91, 10)):
                state = serialized_state(base/f'frame-{frame:04d}.ss0')
                self.assertEqual(int.from_bytes(state[4:8], 'little'), zlib.crc32(rom)&0xffffffff)
                self.assertEqual((state[0x3ba], state[0x3e4]), (7, 0))
                observed.append(sum((state[0x2400+b+i]&7) != policy[state[0x400+b+i]]
                                    for b in (0x1800,0x1c00) for i in range(768)))
            self.assertEqual(observed, counts)
            end = serialized_state(base/'frame-0600.ss0')
            self.assertEqual((end[0x5c80], end[0x3b7], end[0x3ba], end[0x60bb], end[0x3e4]),
                             (11, 2, 0, 118, 0))
            self.assertGreater(end[0x60f1], 0)
            self.assertEqual(hashlib.sha256(end[0x4a00:0x4b00]).hexdigest(),
                             '90b7393e610c67b97cd32664fae294ec76d10fd9a25384e004320b76c4ad4cb4')

    def test_assisted_return_preserves_pause_effect_and_stage_exit(self):
        import csv
        import json
        from verify_pickup_class_palettes import serialized_state
        base = ROOT/'tmp/secret-sound-alias-return-01'
        if not (base/'receipt.json').exists(): self.skipTest('local return evidence unavailable')
        receipt = json.loads((base/'receipt.json').read_text())
        self.assertEqual(receipt['status'], 0)
        self.assertTrue(receipt['observer_memory_writes'])
        self.assertEqual(receipt['rom_sha256'],
                         '877ed7510cd59d79117d160f70493cf4ecff0b1ca822697a3834d119de104f7f')
        self.assertEqual(hashlib.sha256((base/'candidate.gb').read_bytes()).hexdigest(),
                         receipt['rom_sha256'])
        with (base/'item-action.tsv').open() as stream:
            rows = list(csv.DictReader(stream, delimiter='\t'))
        self.assertEqual(len(rows), 12000)
        first = next(r for r in rows if int(r['pause_timer']) > 0)
        self.assertEqual((int(first['frame']), int(first['pause_timer'])), (7261, 60))
        returned = serialized_state(base/'frame-8340.ss0')
        self.assertEqual((returned[0x5c80], returned[0x3ba], returned[0x60f1]), (2, 0, 45))
        end = serialized_state(base/'frame-12000.ss0')
        self.assertEqual((end[0x3ba], end[0x60f1], end[0x3e4]), (0, 0, 0))

    def test_lowhealth_miniboss_replay_attributes(self):
        import zlib
        from verify_pickup_class_palettes import serialized_state, PICKUPS
        base = ROOT/'tmp/secret-sound-alias-miniboss-lowhealth-01'
        if not (base/'candidate.gb').exists():
            self.skipTest('local miniboss evidence unavailable')
        rom = (base/'candidate.gb').read_bytes()
        self.assertEqual(hashlib.sha256(rom).hexdigest(),
                         '877ed7510cd59d79117d160f70493cf4ecff0b1ca822697a3834d119de104f7f')
        policy = [0]*256
        for item in PICKUPS:
            for tile in item.tiles: policy[tile] = item.palette
        for frame in [1]+list(range(30, 481, 30)):
            state = serialized_state(base/f'frame-{frame:04d}.ss0')
            self.assertEqual(int.from_bytes(state[4:8], 'little'), zlib.crc32(rom)&0xffffffff)
            self.assertEqual((state[0x3ba], state[0x3b7], state[0x3bf], state[0x3e4]),
                             (7, 9, 15, 0))
            if frame >= 30: self.assertEqual(state[0x5c80], 11)
            for bank in (0x1800, 0x1c00):
                for i in range(768):
                    self.assertEqual(state[0x2400+bank+i]&7, policy[state[0x400+bank+i]])
        # Damage still occurs; this is not an invulnerability workaround.
        self.assertEqual(state[0x60bb], 78)

    def test_dense_projection_and_sampling_control(self):
        import json
        for name, sparse, visible_bad in (
                ('secret-sound-alias-dense-01', 'secret-sound-alias-lowhealth-01', 0),
                ('secret-sound-alias-parent-dense-01', 'arena-secret-lowhealth-01', 110)):
            base = ROOT/'tmp'/name
            path = base/'alias-map-analysis.json'
            if not path.exists(): self.skipTest('dense local evidence unavailable')
            rows = json.loads(path.read_text())['frames']
            self.assertEqual([r['frame'] for r in rows], list(range(1, 121)))
            self.assertEqual(sum(r['projected_visible_mismatches'] > 0 for r in rows), visible_bad)
            for row in rows:
                state = base/f"frame-{row['frame']:04d}.ss0"
                self.assertEqual(hashlib.sha256(state.read_bytes()).hexdigest(), row['state_sha256'])
                self.assertEqual(row['projected_visible_mismatches'],
                                 sum(m['projected_visible'] for m in row['mismatches']))
            if visible_bad == 0:
                self.assertEqual([(r['frame'], len(r['mismatches'])) for r in rows if r['mismatches']],
                                 [(30, 44)])
            for frame in (1, 30, 60, 90, 120):
                self.assertEqual((base/f'frame-{frame:04d}.png').read_bytes(),
                                 (ROOT/'tmp'/sparse/f'frame-{frame:04d}.png').read_bytes())

    def test_retained_lowhealth_replays_keep_transient_and_broken_control(self):
        import zlib
        from verify_pickup_class_palettes import serialized_state, PICKUPS
        policy = [0]*256
        for item in PICKUPS:
            for tile in item.tiles: policy[tile] = item.palette
        frames = [1] + list(range(30, 481, 30))
        for name, pin, expected in (
                ('arena-secret-lowhealth-01', trial.PARENT, [32]+[88]*16),
                ('secret-sound-alias-lowhealth-01',
                 '877ed7510cd59d79117d160f70493cf4ecff0b1ca822697a3834d119de104f7f',
                 [0, 44]+[0]*15)):
            base = ROOT/'tmp'/name
            if not (base/'candidate.gb').exists():
                self.skipTest('local exact-ROM replay unavailable')
            rom = (base/'candidate.gb').read_bytes()
            self.assertEqual(hashlib.sha256(rom).hexdigest(), pin)
            counts = []
            for frame in frames:
                state = serialized_state(base/f'frame-{frame:04d}.ss0')
                self.assertEqual(int.from_bytes(state[4:8], 'little'), zlib.crc32(rom)&0xffffffff)
                self.assertEqual(state[0x3ba], 7)
                self.assertEqual(state[0x3b7], 9)
                self.assertEqual(state[0x3e4], 0)
                if frame >= 30: self.assertEqual(state[0x5c80], 11)
                counts.append(sum((state[0x2400+b+i]&7) != policy[state[0x400+b+i]]
                                  for b in (0x1800, 0x1c00) for i in range(768)))
            self.assertEqual(counts, expected)

    def test_all_scene_pairs_and_negative_control(self):
        code = trial.gate()
        for raw in range(256):
            for canonical in range(256):
                expected = raw in (9, 10) or raw == 11 and canonical in (9, 10)
                self.assertEqual(route(code, 7, raw, canonical),
                                 'secret' if expected else 'native')
        self.assertEqual(route(trial.old_gate(), 7, 11, 9), 'native')
        self.assertEqual(route(code, 7, 11, 9), 'secret')

    def test_other_stages_stay_native(self):
        for stage in range(256):
            if stage == 7: continue
            for raw in (0, 9, 10, 11, 12, 23, 255):
                self.assertEqual(route(trial.gate(), stage, raw, 9), 'native')

    def test_patch_is_bounded_and_pinned(self):
        path = ROOT/'tmp/arena-completion-safe-source-01/candidate.gb'
        if not path.exists(): self.skipTest('local pinned parent unavailable')
        parent = path.read_bytes()
        result = trial.build(parent)
        self.assertEqual(hashlib.sha256(result).hexdigest(),
                         '877ed7510cd59d79117d160f70493cf4ecff0b1ca822697a3834d119de104f7f')
        allowed = set(range(trial.START, trial.START+len(trial.gate()))) | {0x14e, 0x14f}
        self.assertTrue(all(a == b or i in allowed for i, (a, b) in enumerate(zip(parent, result))))
        with self.assertRaises(ValueError): trial.build(result)


if __name__ == '__main__': unittest.main()
