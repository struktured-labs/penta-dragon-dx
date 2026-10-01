"""#22 current candidate's star rendering, collection and menu return."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
from PIL import Image,ImageChops

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from verify_pickup_class_palettes import serialized_state


class FadeStarRoute(unittest.TestCase):
    def test_star_and_owned_state_chain(self):
        cases=[('live-01',1500,0),('collect-01',120,0),('menu-01',360,1),('resume-02',180,0)]
        states=[];prior=None
        for name,frame,paused in cases:
            p=ROOT/'tmp'/('return-fade16-star-'+name)
            if not (p/'receipt.json').exists():self.skipTest('local star evidence unavailable')
            r=json.loads((p/'receipt.json').read_text())
            self.assertEqual(r['status'],0)
            self.assertEqual(hashlib.sha256((p/'candidate.gb').read_bytes()).hexdigest(),
                             '126dd0b7fff1e03eb6b224f818b85398593c7109ffb676cc538c1bd90742304b')
            if prior is not None:
                self.assertFalse(r['observer_memory_writes'])
                self.assertEqual(r['source_state_sha256'],hashlib.sha256(prior.read_bytes()).hexdigest())
            prior=p/f'frame-{frame:04d}.ss0';s=serialized_state(prior)
            self.assertEqual((s[0x5c80],s[0x3e4]),(2,paused));states.append(s)
        self.assertEqual(states[0][0x60bd:0x60dc],bytes(31))
        # DCD1 is offset 20 from the DCBD inventory base (not offset 19).
        expected=bytearray(31);expected[0xdcd1-0xdcbd]=15
        for s in states[1:]:self.assertEqual(s[0x60bd:0x60dc],expected)
        with Image.open(ROOT/'tmp/return-fade16-star-live-01/frame-1500.png') as source:
            image=source.convert('RGB')
        for point in ((80,84),(80,86),(79,87)):self.assertEqual(image.getpixel(point),(255,255,0))
        for name,identical in (('five-point-star-fixed-live-01',True),('five-point-star-live-01',False)):
            with Image.open(ROOT/'tmp'/name/'frame-1500.png') as ref:
                delta=ImageChops.difference(image.crop((72,80,88,96)),ref.convert('RGB').crop((72,80,88,96)))
            self.assertEqual(delta.getbbox() is None,identical)
        failed=json.loads((ROOT/'tmp/return-fade16-star-resume-01/receipt.json').read_text())
        self.assertEqual(failed['status'],-11)  # Retain failed trial, never count its final PNG as a pass.


if __name__=='__main__':unittest.main()
