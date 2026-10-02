"""#27/#34: retain current-candidate gains and unresolved menu-map failure."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from verify_pickup_class_palettes import serialized_state


class CurrentMapShalamarEvidence(unittest.TestCase):
    def test_low_health_policy_and_unresolved_publication_check(self):
        folder=ROOT/'tmp/current-map-shalamar-phase721-01'
        if not (folder/'completion.json').exists(): self.skipTest('local current-map replay unavailable')
        receipt=json.loads((folder/'completion.json').read_text())
        self.assertTrue(receipt['completed'])
        self.assertEqual(receipt['requested_frames'],1080)
        self.assertEqual(receipt['rom']['sha256'],'916ebb1858c6b9e91491081d82e93d00d283180ef44323f1f29c37a033e48deb')
        self.assertEqual(hashlib.sha256(Path(receipt['rom']['path']).read_bytes()).hexdigest(),receipt['rom']['sha256'])
        self.assertEqual(hashlib.sha256(Path(receipt['state']['path']).read_bytes()).hexdigest(),receipt['state']['sha256'])
        result=json.loads((folder/'verification.json').read_text())
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual([c['status'] for c in result['cycles']],['PASS','FAIL','PASS'])
        self.assertEqual(result['cycles'][1]['map_readiness']['failures'],[{'frame':598,'mismatch_count':8}])
        policy=bytes([0,0]+[4]*253+[0])
        for frame in range(952,1081):
            raw=serialized_state(folder/f'frame-{frame:04d}.ss0')
            self.assertEqual((raw[0x5c80],raw[0x3b7]),(11,12))
            self.assertEqual(raw[0x4a00:0x4b00],policy)
        before=serialized_state(folder/'frame-0597.ss0')
        flagged=serialized_state(folder/'frame-0598.ss0')
        page=0x2000 if flagged[0x340]&8 else 0x1c00
        visible=bytes(flagged[page+r*32+c] for r in range(24) for c in range(24))
        self.assertEqual(visible,before[0x45a0:0x47e0])
        self.assertEqual(sum(a!=b for a,b in zip(visible,flagged[0x45a0:0x47e0])),8)
        # Source-generation overlap is not proof that the rendered publication
        # is correct. Keep the original gate failure pending a publication trace.
