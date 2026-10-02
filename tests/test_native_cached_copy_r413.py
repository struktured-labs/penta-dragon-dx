from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_native_cached_copy_r413 as b


class NativeCachedTests(unittest.TestCase):
    def test_cached_marker_dispatch_and_unchanged_copy_body(self):
        old = b.copier.service(); new = b.copier.service(native_cached=True)
        guard = bytes.fromhex('F0 E0 FE 03 CA')
        at = new.index(guard)
        self.assertEqual(at, 28)
        destination = int.from_bytes(new[at+5:at+7], 'little')-0x6C80
        self.assertEqual(new[destination:], bytes.fromhex('AF 3E 01 C9'))
        self.assertEqual(new[at+7:], old[at:])
        for marker in range(256):
            pc = destination if marker == 3 else at+7
            self.assertEqual(new[pc], 0xAF if marker == 3 else 0xC5)
        # Every preexisting fallback JP still targets the same fallback ABI.
        for i in (5,11,18,25):
            self.assertEqual(int.from_bytes(new[i+1:i+3],'little'),
                             destination+0x6C80)

    def test_scope_and_exact_base(self):
        source = b.BASE.read_bytes(); rom = b.build(source)
        allowed = set(range(b.copier.OFFSET,
                            b.copier.OFFSET+len(b.copier.service(native_cached=True))))
        allowed |= {0x14D,0x14E,0x14F}
        self.assertTrue(all(x == y or i in allowed
                            for i,(x,y) in enumerate(zip(source,rom))))
        with self.assertRaises(ValueError): b.build(bytes(len(source)))


if __name__ == '__main__': unittest.main()
