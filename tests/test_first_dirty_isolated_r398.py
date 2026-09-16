import unittest
from test_first_dirty_source_r397 import b as r397
import build_first_dirty_isolated_r398 as b


class IsolatedTests(unittest.TestCase):
    def test_later_path_and_checked_stage1_entry(self):
        source=b.BASE.read_bytes(); rom=b.build(source)
        self.assertEqual(source[r397.CLONE:r397.CLONE+14],rom[r397.CLONE:r397.CLONE+14])
        for pos in (6,12):
            target=int.from_bytes(source[r397.CLONE+pos:r397.CLONE+pos+2],'little')
            offset=24*0x4000+target-0x4000
            self.assertEqual(source[offset:offset+3],bytes.fromhex('C3 00 73'))
            self.assertEqual(rom[offset:offset+3],source[offset:offset+3])
        self.assertEqual(rom[r397.FALLBACK:r397.FALLBACK+75],source[r397.FALLBACK:r397.FALLBACK+75])
        self.assertEqual(rom[r397.CLONE+14:r397.CLONE+17],bytes.fromhex('C3 0E 74'))
        code,_=r397.clone(source[r397.FALLBACK:r397.FALLBACK+75])
        self.assertEqual(rom[r397.OFFSET:r397.OFFSET+len(code)],code)


if __name__=='__main__': unittest.main()
