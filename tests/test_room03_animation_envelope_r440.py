import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
import build_room03_animation_envelope_r440 as b


class AnimationEnvelope(unittest.TestCase):
    def test_static_verifier_authenticates_new_code_and_rejects_mutations(self):
        from verify_stage1_spike_palettes import semantic_expansion_is_exact
        result = b.build(b.BASE.read_bytes())
        self.assertTrue(semantic_expansion_is_exact(result))
        for site in (b.ENTRY, b.CAVE, b.CAVE+24, b.ENTRY+0x2E):
            modified = bytearray(result)
            modified[site] ^= 1
            self.assertFalse(semantic_expansion_is_exact(bytes(modified)))

    def test_exact_patch_scope(self):
        source = b.BASE.read_bytes()
        result = b.build(source)
        allowed = set(range(b.ENTRY, b.ENTRY+4)) | set(range(b.CAVE, b.CAVE+len(b.helper()))) | {0x14D,0x14E,0x14F}
        self.assertTrue({i for i,(x,y) in enumerate(zip(source,result)) if x!=y} <= allowed)
        self.assertEqual(result[b.ENTRY:b.ENTRY+4], bytes.fromhex('C3 80 43 00'))
        self.assertTrue(b.helper().endswith(bytes.fromhex('F0 40 CB 7F C3 04 43')))
        with self.assertRaises(ValueError):
            b.build(source+b'x')

    def test_machine_normalizer(self):
        # Execute the actual emitted normalizer through its original-entry JP.
        code = b.helper()
        for room in range(256):
            for count in (1,10,11,24):
                a=0; z=False; pc=0; de=0xC220; hl=0x9CA8; c=count
                while True:
                    op=code[pc];pc+=1
                    if op==0xF0:
                        operand=code[pc];pc+=1
                        if operand==0x40: break
                        self.assertEqual(operand,0xE5);a=room
                    elif op==0xFE: z=a==code[pc];pc+=1
                    elif op in (0x20,0x18):
                        delta=code[pc];pc+=1
                        if op==0x18 or not z: pc+=delta if delta<128 else delta-256
                    elif op==0x79: a=c
                    elif op==0x1B: de-=1
                    elif op==0x2B: hl-=1
                    elif op==0x0E: c=code[pc];pc+=1
                    else: self.fail(hex(op))
                shift=4 if room==3 and count==10 else 0
                self.assertEqual((de,hl,c),(0xC220-shift,0x9CA8-shift,14 if room==3 and count in (10,11) else count))
