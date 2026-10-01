import hashlib
import json
import mmap
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
from build_fixed_fade_route_trial import build


class FixedFadeRouteTrial(unittest.TestCase):
    def test_allocation_reference_census_is_not_a_free_space_proof(self):
        parent = (ROOT/'tmp/initial-map-fastpath-trial-01/candidate.gb').read_bytes()
        self.assertEqual(hashlib.sha256(parent).hexdigest(),
                         'ec8be28897810fac01a8918a0403900780015bf6703531f0f82ae259f209f21b')
        # Deliberately byte-shaped, not instruction-boundary-aware. Include
        # immediate pointer loads and absolute reads/stores, not only branches.
        opcodes = {0xC3,0xC2,0xCA,0xD2,0xDA,0xCD,0xC4,0xCC,0xD4,0xDC,
                   0x01,0x11,0x21,0xFA,0xEA}
        mentions = [i for i in range(len(parent)-2)
                    if parent[i] in opcodes
                    and 0xCF <= int.from_bytes(parent[i+1:i+3],'little') < 0xE1]
        self.assertEqual(mentions, [0x8A1F,0x8C58,0x1918A,0x2C2DF,0x2C60F,
                                   0x2CCD9,0x2D4D7,0x2D55B,0x2D763,0x34364,
                                   0x36264,0x40364,0x42264,0x80364,0x82264])
        # These two actual LD HL immediates store the number into DD87/DD88;
        # neither dereferences HL before it is replaced at the later table load.
        for site in (0x8A1F,0x8C58):
            self.assertEqual(parent[site:site+11],
                             bytes.fromhex('21E0007DEA87DD7CEA88DD'))
        relative = [i for i in range(0x3FFF)
                    if parent[i] in (0x18,0x20,0x28,0x30,0x38)
                    and 0xCF <= i+2+int.from_bytes(parent[i+1:i+2],
                                                  'little',signed=True) < 0xE1]
        self.assertEqual(relative, [])
        # Absence of direct branches cannot rule out computed/table references.
        receipt = json.loads((ROOT/'tmp/fixed-fade-route-trial-01/receipt.json').read_text())
        self.assertFalse(receipt['allocation_review_complete'])
        self.assertFalse(receipt['release_qualified'])

    def test_patch_scope_and_pin(self):
        parent = (ROOT/'tmp/initial-map-fastpath-trial-01/candidate.gb').read_bytes()
        rom = build(parent)
        self.assertEqual(hashlib.sha256(rom).hexdigest(),
                         '988b3e07bcfd884c01f7355704a48530502cab157d01d33f2767417ffd9921b7')
        allowed = set(range(0xCF,0xE1)) | set(range(0x15DA,0x15DD)) | set(range(0x75F0,0x75F3)) | {0x14E,0x14F}
        self.assertTrue(all(i in allowed for i,(a,b) in enumerate(zip(parent,rom)) if a!=b))
        self.assertEqual(parent[0x75C7:0x75F0],rom[0x75C7:0x75F0])
        self.assertEqual(parent[0x4068:0x408E],rom[0x4068:0x408E])
        with self.assertRaises(ValueError): build(parent[:-1])

    def test_entry_trace_and_all_captured_images_match_native_control(self):
        trial = ROOT/'tmp/fixed-fade-route-entry-01'
        control = ROOT/'tmp/initial-map-native-control-entry-01'
        self.assertEqual((trial/'trace.tsv').read_bytes(),(control/'trace.tsv').read_bytes())
        frames = sorted(trial.glob('*.png'))
        self.assertEqual(len(frames),38)
        for frame in frames:
            self.assertEqual(frame.read_bytes(),(control/frame.name).read_bytes(),frame.name)

    def test_return_visibility_and_audio_failure_remain_explicit(self):
        receipt = json.loads((ROOT/'tmp/fixed-fade-route-exit-01/receipt.json').read_text())
        self.assertEqual(receipt['rom_sha256'],
                         '988b3e07bcfd884c01f7355704a48530502cab157d01d33f2767417ffd9921b7')
        self.assertEqual(receipt['native_capture']['restored_replay_epoch']['status'],'PASS')
        folder = Path(receipt['native_capture_directory'])
        for name, expected in receipt['native_capture']['hashes'].items():
            with (folder/name).open('rb') as stream:
                self.assertEqual(hashlib.file_digest(stream,'sha256').hexdigest(),expected)
        with (folder/'native.states').open('rb') as sf, (folder/'native.video').open('rb') as vf, mmap.mmap(sf.fileno(),0,access=mmap.ACCESS_READ) as states, mmap.mmap(vf.fileno(),0,access=mmap.ACCESS_READ) as video:
            start = next(i for i in range(6000) if states[i*71680+0x5C80]==2 and states[i*71680+0x3BA]==0)
            self.assertEqual(start+1,4666)
            incomplete, visible = [], []
            for i in range(start,start+100):
                state=states[i*71680:(i+1)*71680]
                page=0x2000 if state[0x340]&8 else 0x1C00
                mismatch=any(state[page+y*32+x]!=state[0x45A0+y*24+x] for y in range(24) for x in range(24))
                white=video[i*92160:(i+1)*92160]==bytes((255,255,255,0))*23040
                if mismatch:
                    incomplete.append(i+1)
                    self.assertTrue(white, f'exposed map at {i+1}')
                if not white: visible.append(i+1)
            self.assertEqual(incomplete,list(range(4666,4671)))
            self.assertEqual(visible[0],4687)
        audio=json.loads((ROOT/'tmp/fixed-fade-route-audio-pair-01/receipt.json').read_text())
        self.assertEqual(audio['status'],'fail')
        self.assertEqual(audio['first_different_sample'],10316126)
        self.assertFalse(audio['checks']['same_digital_silence_intervals'])
        self.assertTrue(audio['checks']['same_full_route_silent_blocks'])


if __name__ == '__main__': unittest.main()
