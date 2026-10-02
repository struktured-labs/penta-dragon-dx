import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_warning_source_tracking_r439 as b


class WarningTracking(unittest.TestCase):
    def test_scope_and_unmoved_control_flow(self):
        source=b.BASE.read_bytes();result=b.build(source)
        allowed={0x14D,0x14E,0x14F}
        for bank,address,code in b.blocks():
            offset=b.prior.offset(bank,address)
            allowed.update(range(offset+code.index(b.OLD),offset+code.index(b.OLD)+5))
            self.assertEqual(result[offset:offset+len(code)],code.replace(b.OLD,b.NEW))
        self.assertTrue(all(i in allowed for i,(x,y) in enumerate(zip(source,result)) if x!=y))
        with self.assertRaises(ValueError):b.build(source+b'mutation')
