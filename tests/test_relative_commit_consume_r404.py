import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_relative_commit_consume_r404 as b

class ConsumeTests(unittest.TestCase):
    def test_exact_identity_and_mutation_rejection(self):
        from verify_stage1_spike_palettes import publication_boundary
        from verify_stage1_north_integrity import detect_publication_boundary
        rom=b.build(b.BASE.read_bytes())
        self.assertEqual(publication_boundary(rom)['variant'],'r404-relative-consume-607dd536')
        self.assertEqual(detect_publication_boundary(rom)['publication_pc'],0x7457)
        self.assertEqual(rom[0x37462:0x37464],bytes.fromhex('E0 40'))
        for offset in (b.OFFSET,0x37464,0x12FC,0x77777):
            changed=bytearray(rom);changed[offset]^=1
            with self.assertRaises(RuntimeError):publication_boundary(changed)

    def test_emitted_tail_and_guard_exit_for_all_ly_lcdc(self):
        rom=b.build(b.BASE.read_bytes())
        for ly in range(256):
            for lcd in range(256):
                pc=b.OFFSET;a=0;z=False;mem={0xC4:0x4C,0x40:lcd,0x44:ly}
                for _ in range(30):
                    if pc==0x36F1D:break
                    op=rom[pc];pc+=1
                    if op==0xAF:a=0;z=True
                    elif op in (0xF0,0xE0):
                        n=rom[pc];pc+=1
                        if op==0xF0:a=mem[n]
                        else:mem[n]=a
                    elif op in (0xEE,0xE6,0xFE):
                        n=rom[pc];pc+=1
                        if op==0xEE:a^=n
                        elif op==0xE6:a&=n
                        z=(a==n) if op==0xFE else (a==0)
                    elif op in (0xC3,0xC2,0xCA):
                        dest=int.from_bytes(rom[pc:pc+2],'little');pc+=2
                        if op==0xC3 or (op==0xC2 and not z) or (op==0xCA and z):pc=0x30000+dest
                    else:raise AssertionError(hex(op))
                else:self.fail('did not return to ISR continuation')
                self.assertEqual(mem,{0xC4:0,0x40:lcd^0x48,0x44:ly})

if __name__=='__main__':unittest.main()
