"""Issue #45 deadline scheduling: local evidence, not release acceptance."""
import hashlib
import csv
import json
import mmap
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
from build_return_card_deadline_trial import build, payload


class CardDeadlineTrial(unittest.TestCase):
    def test_observer_neutrality_palette_window_and_sound_latency(self):
        names = ('return-fade-sound-trial-14', 'return-fade-sound-trial-control-14')
        receipts = []
        for name in names:
            base = ROOT/'tmp'/name
            if not (base/'receipt.json').exists():
                self.skipTest('local timing replay unavailable')
            r = json.loads((base/'receipt.json').read_text())
            self.assertFalse(r['observer_memory_writes'])
            self.assertEqual(r['rom_sha256'], '8ac7fbe3b290f4743280961541fb81746046e89bbdabde6f2b914e73fd60888c')
            for file, digest in r['native_capture']['hashes'].items():
                with (Path(r['native_capture_directory'])/file).open('rb') as stream:
                    self.assertEqual(hashlib.file_digest(stream, 'sha256').hexdigest(), digest)
            receipts.append(r)
        self.assertEqual(receipts[0]['source_state_sha256'], receipts[1]['source_state_sha256'])
        self.assertEqual(receipts[0]['native_capture']['hashes'], receipts[1]['native_capture']['hashes'])
        self.assertEqual((ROOT/'tmp'/names[0]/'inputs.tsv').read_bytes(),
                         (ROOT/'tmp'/names[1]/'inputs.tsv').read_bytes())
        with (ROOT/'tmp'/names[0]/'cram-timing.tsv').open() as stream:
            rows = list(csv.DictReader(stream, delimiter='\t'))
        self.assertEqual(len(rows), 640)  # Includes128 later OBJ writes; do not discard them.
        fade = [r for r in rows if r['bank'] == '14']
        self.assertEqual(len(fade), 512)
        self.assertTrue(all(r['mode'] == '1' and 144 <= int(r['ly']) <= 147 for r in fade))
        commands = []
        for name in ('return-fade-sound-parent-01', names[0]):
            with (ROOT/'tmp'/name/'sound-commands.tsv').open() as stream:
                commands.append([r for r in csv.DictReader(stream, delimiter='\t') if r['command'] == '13'])
        for rows in commands:
            self.assertEqual([r['event'] for r in rows], ['request', 'read', 'accept'])
            self.assertTrue(all(r['frame'] == '120' for r in rows))
        self.assertEqual([int(b['cycle'])-int(a['cycle']) for a,b in zip(*commands)], [8,8,8])

    def test_bounded_patch_and_four_deadlines(self):
        path = ROOT / 'tmp/return-cgb-fade-trial-10/candidate.gb'
        if not path.exists():
            self.skipTest('parent unavailable')
        parent = path.read_bytes()
        result = build(parent)
        self.assertEqual(hashlib.sha256(result).hexdigest(),
                         '8ac7fbe3b290f4743280961541fb81746046e89bbdabde6f2b914e73fd60888c')
        code = payload()
        self.assertEqual(code.count(bytes.fromhex('F0 D4 FE 04 38 FA')), 4)
        self.assertTrue(all(i in (0x14e, 0x14f) or 0x516ae <= i < 0x516b1
                            or 0x51c20 <= i < 0x51c20+len(code)
                            for i, (a, b) in enumerate(zip(parent, result)) if a != b))

    def test_resume_cadence_and_white_initialization(self):
        paths = [Path('/mnt/data/tmp') / ('penta-'+name+'-av') for name in
                 ('return-initial-map-exit-01', 'return-cgb-fade-exit-14')]
        if not all((p/'native.states').exists() for p in paths):
            self.skipTest('local captures unavailable')
        white = []
        for p in paths:
            with (p/'native.states').open('rb') as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as s:
                dungeon = next(i+1 for i in range(4600, 4900)
                               if s[i*71680+0x5c80] == 2 and s[i*71680+0x3ba] == 0)
                active = next(i+1 for i in range(dungeon-1, 4900) if s[i*71680+0x3e4] == 0)
                self.assertEqual((dungeon, active), (4801, 4858))
                white.append(all(s[i*71680+0xd4:i*71680+0x114] == bytes.fromhex('FF7F')*32
                                 for i in range(4800, 4818)))
        self.assertEqual(white, [False, True])
        receipt = json.loads((ROOT/'tmp/return-cgb-fade-audio-pair-14/receipt.json').read_text())
        self.assertEqual(receipt['status'], 'fail')
        self.assertTrue(receipt['checks']['same_full_route_silent_blocks'])
        self.assertFalse(receipt['checks']['same_digital_silence_intervals'])


if __name__ == '__main__':
    unittest.main()
