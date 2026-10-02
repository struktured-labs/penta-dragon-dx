"""#35: direct LCD-write evidence for the retained title duration difference."""
import csv
import hashlib
import json
from pathlib import Path
import unittest
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from verify_pickup_class_palettes import serialized_state


class TitleLcdExitTiming(unittest.TestCase):
    def test_same_title_choice_not_a_missed_button(self):
        traces=[]
        for name in ('parent','guard'):
            p=ROOT/f'tmp/title-input-{name}-01'
            reference=ROOT/f'tmp/title-lcd-exit-{name}-01'
            if not (p/'receipt.json').exists():
                self.skipTest('local title input trace unavailable')
            receipt=json.loads((p/'receipt.json').read_text())
            self.assertEqual(receipt['status'],0)
            self.assertFalse(receipt['observer_memory_writes'])
            self.assertEqual((p/'candidate.gb').read_bytes(),(reference/'candidate.gb').read_bytes())
            self.assertEqual((p/'inputs.tsv').read_bytes(),(reference/'inputs.tsv').read_bytes())
            self.assertEqual((p/'trace.tsv').read_bytes(),(reference/'trace.tsv').read_bytes())
            images=sorted(p.glob('frame-*.png'))
            self.assertEqual(len(images),210)
            for image in images:
                self.assertEqual(image.read_bytes(),(reference/image.name).read_bytes())
                self.assertEqual(serialized_state(image.with_suffix('.ss0')),
                                 serialized_state((reference/image.name).with_suffix('.ss0')))
            with (p/'title-input-timing.tsv').open() as stream:
                rows=list(csv.DictReader(stream,delimiter='\t'))
            self.assertEqual(len(rows),7)
            accepted=rows[-3]
            self.assertEqual(tuple(accepted[k] for k in ('frame','pc','a','f','joy','edge')),
                             ('194','3B26','02','10','01','01'))
            traces.append(rows)
        # Same native choice/carry and A edge. Timing phase differs before it.
        for x,y in zip(*traces):
            for key in ('frame','pc','a','f','sp','joy','edge','scene'):
                self.assertEqual(x[key],y[key])
        self.assertEqual([r['tick'] for r in (traces[0][-3],traces[1][-3])],['91','90'])
        self.assertEqual(int(traces[1][-3]['cycle'])-int(traces[0][-3]['cycle']),-53448)

    def test_direct_lcd_exit_precedes_frame_clock_delta(self):
        captures=[]
        for name,pin in (
            ('parent','106c2e0181fa9bee1b3777f82af61d49d181415dafdd0456fea2c56a8234e317'),
            ('guard','8ff1c98d98f6949d39628c0c9fc86a53aae805f25cb8936484f2a00893af5c3c')):
            p=ROOT/f'tmp/title-lcd-exit-{name}-01'
            if not (p/'receipt.json').exists():
                self.skipTest('local direct LCD traces unavailable')
            receipt=json.loads((p/'receipt.json').read_text())
            self.assertEqual(receipt['status'],0)
            self.assertFalse(receipt['observer_memory_writes'])
            self.assertEqual(hashlib.sha256((p/'candidate.gb').read_bytes()).hexdigest(),pin)
            with (p/'return-publication.tsv').open() as stream:
                rows=[r for r in csv.DictReader(stream,delimiter='\t') if r['address']=='FF40']
            self.assertEqual(len(rows),9)
            captures.append((p,rows))
        (a,ar),(b,br)=captures
        self.assertEqual((a/'inputs.tsv').read_bytes(),(b/'inputs.tsv').read_bytes())
        self.assertEqual([(r['frame'],r['old'],r['new'],r['pc']) for r in ar],
                         [(r['frame'],r['old'],r['new'],r['pc']) for r in br])
        deltas=[int(y['cycle'])-int(x['cycle']) for x,y in zip(ar,br)]
        self.assertEqual(deltas,[0,0,0,4032,4032,-53448,-53448,-53448,-53448])
        self.assertEqual((ar[5]['frame'],ar[5]['pc'],ar[5]['new']),('194','53CF','00'))
        self.assertEqual((ar[5]['ly'],br[5]['ly']),('101','38'))
        # This proves a real clock difference, not missing capture samples.
        # It does not establish the cause upstream or qualify audio fidelity.


if __name__=='__main__':unittest.main()
