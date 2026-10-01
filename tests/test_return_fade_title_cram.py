"""#35: current cold-title access safety, with observer differences retained."""
import csv
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from check_cram_timing import check
from normalize_mgba_state_pc import png_chunks
from verify_pickup_class_palettes import serialized_state


class ReturnTitleCram(unittest.TestCase):
    def test_current_title_writes_and_observer_pair(self):
        observed=ROOT/'tmp/return-fade16-title-cram-01'
        control=ROOT/'tmp/return-fade16-title-control-01'
        if not all((p/'receipt.json').exists() for p in (observed,control)):
            self.skipTest('local exact title evidence unavailable')
        for p in (observed,control):
            receipt=json.loads((p/'receipt.json').read_text())
            self.assertEqual(receipt['status'],0)
            self.assertFalse(receipt['observer_memory_writes'])
            self.assertEqual(hashlib.sha256((p/'candidate.gb').read_bytes()).hexdigest(),
                             '126dd0b7fff1e03eb6b224f818b85398593c7109ffb676cc538c1bd90742304b')
        with (observed/'cram-timing.tsv').open() as stream:
            rows=list(csv.DictReader(stream,delimiter='\t'))
        result=check(rows)
        self.assertEqual(result['writes'],2984)
        self.assertEqual(result['status'],'PASS_OBSERVED_WRITES')
        mutation=[dict(r) for r in rows]
        mutation[0].update(lcdc='80',mode='3')
        self.assertEqual(check(mutation)['status'],'FAIL')
        for name in ('trace.tsv','inputs.tsv'):
            self.assertEqual((observed/name).read_bytes(),(control/name).read_bytes())
        screenshots=sorted(observed.glob('frame-*.png'))
        self.assertEqual(len(screenshots),11)
        for image in screenshots:
            self.assertEqual(image.read_bytes(),(control/image.name).read_bytes())
            a=image.with_suffix('.ss0');b=(control/image.name).with_suffix('.ss0')
            self.assertEqual(serialized_state(a),serialized_state(b))
            # Full files differ: retain and identify metadata, not full-file equality.
            self.assertNotEqual(a.read_bytes(),b.read_bytes())
            ca,cb=list(png_chunks(a.read_bytes())),list(png_chunks(b.read_bytes()))
            self.assertEqual([k for k,_ in ca],[k for k,_ in cb])
            differences=[(x,y) for x,y in zip(ca,cb) if x!=y]
            self.assertEqual(len(differences),1)
            for x,y in differences:
                self.assertEqual(x[0],b'gbAx')
                self.assertEqual(x[1][:8],bytes.fromhex('0101000008000000'))
                self.assertEqual(y[1][:8],x[1][:8])


if __name__=='__main__':unittest.main()
