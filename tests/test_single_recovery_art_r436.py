import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
import build_single_recovery_art_r436 as builder


class SingleArtUpload(unittest.TestCase):
    def test_scope_and_complete_upload_preimages(self):
        source = builder.BASE.read_bytes()
        result = builder.build(source)
        allowed = set(range(builder.SITE, builder.SITE+13)) | {0x14D,0x14E,0x14F}
        self.assertTrue(all(i in allowed for i,(a,b) in enumerate(zip(source,result)) if a != b))
        self.assertEqual(result[builder.SITE:builder.SITE+13], builder.original.ENTRY_NEW)
        with self.assertRaises(ValueError):
            builder.build(source[:-1])
