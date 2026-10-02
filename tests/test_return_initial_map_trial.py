"""#45 builder/mapper ABI checks; emulator visual acceptance still required."""
import hashlib
import json
import mmap
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
from build_return_initial_map_trial import build, OFFSET, OLD, PREFIX


class InitialMapTrial(unittest.TestCase):
    def test_full_return_map_window_and_retained_timing_difference(self):
        results = {}
        cases = (
            ('parent', 'return-initial-map-parent-exit-01',
             '2b797a6af30598141d874a8a272e9a7c77012044fe82f649f1b3e9142d31f306',53),
            ('trial', 'return-initial-map-exit-01',
             '916ebb1858c6b9e91491081d82e93d00d283180ef44323f1f29c37a033e48deb',4),
        )
        for label,name,pin,bad_frames in cases:
            base = ROOT/'tmp'/name
            if not (base/'receipt.json').exists():
                self.skipTest('local matched return evidence unavailable')
            receipt = json.loads((base/'receipt.json').read_text())
            self.assertEqual(receipt['status'],0)
            self.assertEqual(hashlib.sha256((base/'candidate.gb').read_bytes()).hexdigest(),pin)
            self.assertTrue(receipt['observer_memory_writes'])  # health-assisted, not combat acceptance
            native = Path(receipt['native_capture_directory'])
            with (native/'native.states').open('rb') as stream, mmap.mmap(stream.fileno(),0,access=mmap.ACCESS_READ) as data:
                self.assertEqual(len(data),6000*71680)
                self.assertEqual(hashlib.sha256(data).hexdigest(), receipt['native_capture']['hashes']['native.states'])
                start = next(i for i in range(6000) if data[i*71680+0x5c80]==2 and data[i*71680+0x3ba]==0)
                mismatches, shades = [], []
                for i in range(start,start+65):
                    s = data[i*71680:(i+1)*71680]
                    page = 0x2000 if s[0x340]&8 else 0x1c00
                    mismatches.append(sum(s[page+r*32+c] != s[0x45a0+r*24+c]
                                          for r in range(24) for c in range(24)))
                    shades.append(s[0x347])
                self.assertEqual(sum(n>0 for n in mismatches),bad_frames)
                self.assertTrue(all(n==0 for n in mismatches[bad_frames:]))
                results[label] = [(i,v) for i,v in enumerate(shades) if i==0 or v!=shades[i-1]]
        # Do not call this timing parity: the trial adds one frame in this route.
        self.assertEqual(results['parent'],[(0,0),(20,0x40),(28,0x90),(36,0xe4)])
        self.assertEqual(results['trial'],[(0,0),(20,0x40),(29,0x90),(37,0xe4)])

    def test_prefix_returns_bank_one_with_zero_only_when_inactive(self):
        for active in range(256):
            pc, a, z, returned = 0, 0, False, False
            while pc < len(PREFIX):
                op = PREFIX[pc]
                if op == 0xf0:
                    self.assertEqual(PREFIX[pc+1], 0xc1)
                    a = active
                    pc += 2
                elif op == 0xb7:
                    z = a == 0
                    pc += 1
                elif op == 0x20:
                    pc += 2 + (PREFIX[pc+1] if not z else 0)
                elif op == 0x3e:
                    a = PREFIX[pc+1]
                    pc += 2
                elif op == 0xc9:
                    returned = True
                    break
                else:
                    self.fail(f'unmodeled opcode {op:02x}')
            self.assertEqual(returned, active == 0)
            if returned:
                self.assertEqual((a,z), (1,True))
            else:
                self.assertEqual(pc, len(PREFIX))

    def test_exact_parent_and_change_scope(self):
        path = ROOT/'tmp/secret-alias-chunk-trial-01/candidate.gb'
        if not path.exists(): self.skipTest('local pinned ROM unavailable')
        parent = path.read_bytes()
        result = build(parent)
        self.assertEqual(result[OFFSET:OFFSET+len(PREFIX)+len(OLD)], PREFIX+OLD)
        allowed = {0x14e,0x14f} | set(range(OFFSET,OFFSET+len(PREFIX)+len(OLD)))
        self.assertTrue(all(i in allowed for i,(a,b) in enumerate(zip(parent,result)) if a!=b))
        self.assertEqual(hashlib.sha256(result).hexdigest(),
                         '916ebb1858c6b9e91491081d82e93d00d283180ef44323f1f29c37a033e48deb')
        with self.assertRaises(ValueError): build(result)
