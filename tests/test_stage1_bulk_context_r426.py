import unittest
from unittest.mock import patch
import test_stage1_bulk_compile_r425 as machine
import build_stage1_bulk_context_r426 as b

class ContextCompile(unittest.TestCase):
    def test_unbanked_context_and_equivalence(self):
        code=b.service()
        self.assertEqual(code[6:11],bytes.fromhex('F0 B7 00 FE 02'))
        # No banked scene read. Entry receives SVBK3, where D880 is not
        # the sound engine's physical bank1 scene byte.
        self.assertNotIn(bytes.fromhex('FA 80 D8'),code)
        for stage,context in ((0,2),(0,11),(0,0),(1,2),(4,6),(6,8)):
            original=machine.execute(stage,context)
            with patch.object(machine.b,'service',lambda:code):
                result=machine.execute(stage,context)
            self.assertEqual(result,original)
        # Reproduce the actual address-space distinction: context2 is live,
        # but bank3:D880 contains unrelated data. r425 falls back; r426 runs.
        old_regs,old_mem,before=machine.execute(0,2,banked_scene=255)
        self.assertEqual(old_mem,before)
        self.assertEqual(old_regs[2:5],(0xD0,0,0xC1A0))
        with patch.object(machine.b,'service',lambda:code):
            regs,mem,_=machine.execute(0,2,banked_scene=255)
        self.assertEqual(regs[2:5],(0xD3,0,0xC3E0))
        self.assertEqual(mem[0xDFE2:0xDFE4],bytes.fromhex('24 43'))
        source=b.BASE.read_bytes();rom=b.build(source)
        old=b.prior.build(source)
        allowed={b.prior.OFFSET+i for i in (6,7,8)}|{0x14D,0x14E,0x14F}
        self.assertTrue(all(x==y or i in allowed for i,(x,y) in enumerate(zip(old,rom))))

if __name__=='__main__':unittest.main()
