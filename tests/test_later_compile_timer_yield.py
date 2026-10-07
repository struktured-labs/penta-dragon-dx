"""#59 execute emitted compiler bytes; emulator qualification remains required."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_later_compile_timer_yield as b


def execute(raw=11, canonical=3, stage=1, ie=4):
    code=b.helper();pc=0;sp=0xDFF5;bank=3
    a,c,hl,de,z,carry=0,0,0xD000,0xC1A0,False,False
    mem=bytearray((i*37+i//7)&255 for i in range(65536))
    mem[sp:sp+4]=bytes.fromhex('4D080E43')
    mem[0xFFFF]=ie;mem[0xFFB7]=canonical;mem[0xFFBA]=stage
    before=bytes(mem);windows=0;pending=False
    def imm():
        nonlocal pc
        value=code[pc];pc+=1;return value
    for _ in range(5000):
        op=imm()
        if op==0xF0:a=mem[0xFF00+imm()]
        elif op==0xFA:
            address=imm()+256*imm();assert address==0xD880 and bank==1
            a=raw
        elif op==0xFE:
            v=imm();z=a==v;carry=a<v
        elif op==0xD6:
            v=imm();carry=a<v;a=(a-v)&255;z=a==0
        elif op in (0xC2,0xD2,0xC3):
            dest=imm()+256*imm()
            if op==0xC3 or (op==0xC2 and not z) or (op==0xD2 and not carry):
                if dest==b.RETURN:return mem,before,windows,(1,hl,de,sp,bank)
                pc=dest-b.ENTRY
        elif op in (0x20,0x28,0x30,0x38):
            delta=imm();delta=delta if delta<128 else delta-256
            if {0x20:not z,0x28:z,0x30:not carry,0x38:carry}[op]:pc+=delta
        elif op==0x3E:a=imm()
        elif op==0xE0:
            address=imm()
            if address==0x70:bank=a
            else:mem[0xFF00+address]=a
        elif op==0xEA:
            address=imm()+256*imm();assert address==0xD47F and bank==3
            mem[address]=a
        elif op==0x1A:a=mem[de]
        elif op==0x13:de+=1
        elif op==0x4F:c=a
        elif op==0x0A:a=mem[0xC600+c]
        elif op==0x22:
            assert bank==3;mem[hl]=a;hl+=1
        elif op==0xFB:
            assert ie==4 and bank==1;pending=True
        elif op==0:
            assert pending and bank==1;windows+=1
        elif op==0xF3:
            assert pending and bank==1;pending=False
        elif op==0x7D:a=hl&255
        elif op==0xC6:
            v=imm();carry=a+v>255;a=(a+v)&255;z=a==0
        elif op==0x6F:hl=(hl&0xFF00)|a
        elif op==0x24:hl+=256;z=hl>>8==0
        elif op==0x3D:a=(a-1)&255;z=a==0
        elif op==0xE5:
            assert bank==3;sp-=2;mem[sp:sp+2]=hl.to_bytes(2,'little')
        elif op==0xF8:hl=sp+imm()
        elif op==0x36:mem[hl]=imm()
        elif op==0x23:hl+=1
        elif op==0xE1:hl=int.from_bytes(mem[sp:sp+2],'little');sp+=2
        elif op==0xAF:a=0;z=True;carry=False
        elif op==0xC9:
            assert bank==3 and mem[sp:sp+2]==bytes.fromhex('4D08')
            return mem,before,windows,(a,hl,de,sp,bank)
        else:raise AssertionError(hex(op))
    raise AssertionError('unterminated compiler')


class TimerYield(unittest.TestCase):
    def test_cells_padding_stack_and_interrupt_windows(self):
        for canonical in range(3,9):
            mem,before,windows,regs=execute(canonical=canonical,stage=canonical-2)
            expected=bytearray(before)
            for row in range(24):
                for col in range(24):
                    expected[0xD000+32*row+col]=before[0xC600+before[0xC1A0+24*row+col]]
            if canonical==3:expected[0xD47F]=0
            expected[0xDFF3:0xDFF5]=bytes.fromhex('00D3')
            expected[0xDFF7:0xDFF9]=bytes.fromhex('2443')
            expected[0xFFE0]=0
            self.assertEqual(mem,expected)
            self.assertEqual(windows,24)
            self.assertEqual(regs,(1,0xD300,0xC3E0,0xDFF5,3))

    def test_all_non_timer_only_interrupt_masks_decline(self):
        for ie in range(256):
            if ie==4:continue
            mem,before,windows,_=execute(ie=ie)
            self.assertEqual(mem,before);self.assertEqual(windows,0)

    def test_normal_and_non_dungeon_scenes_decline(self):
        for raw in range(256):
            if raw==11:continue
            mem,before,windows,regs=execute(raw=raw)
            self.assertEqual(mem,before);self.assertEqual(windows,0)
            self.assertEqual(regs[-1],3)
        for scene in range(256):
            if 3<=scene<=8:continue
            mem,before,windows,_=execute(canonical=scene)
            self.assertEqual(mem,before);self.assertEqual(windows,0)

    def test_wrong_parent_rejected(self):
        with self.assertRaises(ValueError):b.build(bytes(1048576))


if __name__=='__main__':unittest.main()
