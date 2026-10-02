import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
from check_pipeline_attribute_snapshots import analyze

class AttributeSnapshots(unittest.TestCase):
    def test_complete_lookup_and_mutation(self):
        source=bytes(i%256 for i in range(576));lut=bytes(reversed(range(256)))
        plane=bytearray(768)
        for row in range(24):
            for col in range(24):plane[row*32+col]=lut[source[row*24+col]]
        snapshot=source+lut+plane+bytes(121)
        self.assertEqual(analyze(snapshot)['mismatch_cells'],0)
        bad=bytearray(snapshot);bad[832+32]^=1
        self.assertEqual(analyze(bad)['mismatch_cells'],1)
        for malformed in (b'',snapshot[:-1]):
            with self.assertRaises(ValueError):analyze(malformed)

if __name__=='__main__':unittest.main()
