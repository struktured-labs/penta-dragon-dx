"""#45 experimental orchestration scope; emulator acceptance is separate."""
import hashlib
import csv
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
import build_return_only_fade_trial as builder


class ReturnOnlyFade(unittest.TestCase):
    def test_native_chain_keeps_original_callees_and_failed_timing(self):
        p = ROOT/'tmp/initial-map-fastpath-trial-01/candidate.gb'
        if not p.exists(): self.skipTest('local exact parent unavailable')
        old = p.read_bytes()
        new, labels = builder.build(old, direct_sound_request=True, native_card_chain=True)
        self.assertEqual(hashlib.sha256(new).hexdigest(),
                         '62ed16109187ea84b7cade8e2c36fcb128d4ffa020cf49ce750f720d605117b3')
        for start, end in ((0x0F47,0x0F65),(0x4068,0x408E)):
            self.assertEqual(new[start:end], old[start:end])
        self.assertIn('card_native_chain', labels)
        with self.assertRaises(ValueError):
            builder.build(old, local_card_waits=True, native_card_chain=True)
        trace = ROOT/'tmp/return-native-chain-exit-prefix-01/sound-commands.tsv'
        if not trace.exists(): self.skipTest('local prefix capture unavailable')
        with trace.open() as f:
            rows = [r for r in csv.DictReader(f,delimiter='\t')
                    if r['command']=='13' and int(r['frame'])>4000]
        self.assertEqual([(r['event'],r['cycle']) for r in rows if r['event']!='read'],
                         [('request','1161391592'),('accept','1161408856')])

    def test_local_waits_retain_native_counts_and_instruction_bodies(self):
        p = ROOT/'tmp/initial-map-fastpath-trial-01/candidate.gb'
        if not p.exists(): self.skipTest('local exact parent unavailable')
        old = p.read_bytes()
        new, labels = builder.build(old, direct_sound_request=True, local_card_waits=True)
        self.assertEqual(hashlib.sha256(new).hexdigest(),
                         '24b78374dc8dc55f24778b2688ac7d60e47b953881a0394f484e34559859a729')
        def at(name, length):
            offset = 20*16384 + labels[name]-0x4000
            return new[offset:offset+length]
        self.assertEqual(at('card_native_tick_wait',15),old[0x406F:0x407E])
        self.assertEqual(at('card_native_mode_wait',16),old[0x407E:0x408E])
        self.assertEqual(at('card_native_fade',8),old[0x0F47:0x0F4F])
        self.assertEqual(at('card_native_waits',7)[3:],old[0x406B:0x406F])
        self.assertNotIn('native_01_0f47',labels)
        self.assertNotIn('native_01_4068',labels)
        card = at('card',labels['fade']-labels['card'])
        self.assertIn(bytes.fromhex('0664'),card)  # original100 waits, not a shortened delay

    def test_direct_request_uses_original_fixed_rst_sequence(self):
        p = ROOT/'tmp/initial-map-fastpath-trial-01/candidate.gb'
        if not p.exists(): self.skipTest('local exact parent unavailable')
        old = p.read_bytes()
        new, labels = builder.build(old, direct_sound_request=True)
        self.assertEqual(hashlib.sha256(new).hexdigest(),
                         '73ee08d7b5ad4f2af16a0e5c297856150908af76a0d2543ec0865ffcafcfb770')
        self.assertNotIn('native_01_0038', labels)
        start = 20*16384 + labels['loader']-0x4000
        end = 20*16384 + labels['card']-0x4000
        self.assertTrue(new[start:end].endswith(bytes.fromhex('F5 3E13 FF F1 F0B7 EA80D8 C9')))
        self.assertEqual(new[0x38:0x3C], old[0x38:0x3C])
        # Existing experiment stays exactly reproducible; the option is explicit.
        self.assertEqual(hashlib.sha256(builder.build(old)[0]).hexdigest(),
                         '9c7e4f94a5dcb898faac58c9f9af66a416fa92be6b6843b1468549d3f61788ea')

    def test_entry_route_matches_control_but_cycles_are_not_identical(self):
        control = ROOT/'tmp/secret-fade-native-timing-01'
        trial = ROOT/'tmp/return-only-fade-entry-02'
        broken = ROOT/'tmp/return-only-fade-entry-01'
        if not (trial/'receipt.json').exists(): self.skipTest('local replay unavailable')
        receipt = json.loads((trial/'receipt.json').read_text())
        self.assertEqual(receipt['rom_sha256'],
                         '9c7e4f94a5dcb898faac58c9f9af66a416fa92be6b6843b1468549d3f61788ea')
        self.assertEqual((trial/'trace.tsv').read_bytes(), (control/'trace.tsv').read_bytes())
        self.assertNotEqual((broken/'trace.tsv').read_bytes(), (control/'trace.tsv').read_bytes())
        pictures = list(trial.glob('frame-*.png'))
        self.assertEqual(len(pictures), 31)
        for picture in pictures:
            self.assertEqual(picture.read_bytes(), (control/picture.name).read_bytes())
        def rows(folder):
            with (folder/'secret-fade-timing.tsv').open() as f:
                return {r['pc']:r for r in csv.DictReader(f, delimiter='\t')}
        c, t = rows(control), rows(trial)
        self.assertEqual(t['15DD'], c['15DD'])
        self.assertEqual(int(t['0F33']['cycle'])-int(c['0F33']['cycle']), 40)
        self.assertEqual(int(t['0F7A']['cycle'])-int(c['0F7A']['cycle']), 8)
        # Contrary to the initial hypothesis,1498 also executes on entry.
        self.assertEqual((t['1498']['scene'], t['1498']['stage']), ('02','00'))

    def test_restored_shared_calls_and_exact_change_scope(self):
        p = ROOT/'tmp/initial-map-fastpath-trial-01/candidate.gb'
        if not p.exists(): self.skipTest('local exact parent unavailable')
        old = p.read_bytes(); new, labels = builder.build(old)
        self.assertEqual(hashlib.sha256(new).hexdigest(),
                         '9c7e4f94a5dcb898faac58c9f9af66a416fa92be6b6843b1468549d3f61788ea')
        self.assertEqual(new[0x15DA:0x15DD], bytes.fromhex('CD7A0F'))
        self.assertEqual(new[0x75F0:0x75F3], bytes.fromhex('C3330F'))
        self.assertEqual(new[0xC7:0xCF], old[0xC7:0xCF])
        body, _ = builder.payload()
        offset = 20*16384 + builder.BASE-0x4000
        allowed = set(range(offset, offset+len(body)))
        for start, size in ((0xC1,6),(0x1498,6),(0x15DA,3),(0x75F0,3),(0x14E,2)):
            allowed.update(range(start,start+size))
        self.assertTrue(all(i in allowed for i,(x,y) in enumerate(zip(old,new)) if x != y))
        self.assertEqual(new[20*16384+0x151C:20*16384+0x1C89],
                         old[20*16384+0x151C:20*16384+0x1C89])
        self.assertIn('stage_zero', labels)
        with self.assertRaises(ValueError): builder.build(new)


if __name__ == '__main__': unittest.main()
