"""#27 execute the mapper and entry bytes with a real banked address window."""
import hashlib
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('bank_rearm', Path(__file__).resolve().parents[1]/'scripts/diagnostics/build_boss_prelude_bank_rearm.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class BankRearmTests(unittest.TestCase):
    def setUp(self):
        self.parent = bytearray([0xD3]) * 0x100000
        for start, text in ((0x1A43,'CD9A7C000000'), (0x7C9A,'3E01E091E0DAE0E4C9'),
                            (0x28,'C39A09'), (0x99A,'F53E01CD6100F1C9'),
                            (0x61,'EA09DCC3BE09'), (0x9BE,'E099EA0021C9')):
            data = bytes.fromhex(text)
            self.parent[start:start+len(data)] = data

    def build(self):
        with patch.object(m,'PARENT',hashlib.sha256(self.parent).hexdigest()):
            return m.build(self.parent)

    def execute(self, rom, bank, flags):
        mem = bytearray(65536)
        mem[0xFF99] = bank
        pc, sp, a, f, cycles = 0x1A43, 0xDFE0, 0x6D, flags, 0
        def read(address):
            if address < 0x4000:
                return rom[address]
            if address < 0x8000:
                return rom[bank*0x4000+address-0x4000]
            return mem[address]
        def push(value):
            nonlocal sp
            sp -= 2
            mem[sp:sp+2] = value.to_bytes(2,'little')
        def pop():
            nonlocal sp
            value = int.from_bytes(mem[sp:sp+2],'little')
            sp += 2
            return value
        for _ in range(50):
            if pc == 0x1A49:
                return a,f,sp,bank,cycles,mem
            op=read(pc);pc+=1
            if op == 0xEF:
                push(pc);pc=0x28;cycles+=16
            elif op == 0xF5:
                push(a<<8|f);cycles+=16
            elif op == 0xF1:
                value=pop();a=value>>8;f=value&0xF0;cycles+=12
            elif op == 0x3E:
                a=read(pc);pc+=1;cycles+=8
            elif op == 0xE0:
                mem[0xFF00+read(pc)]=a;pc+=1;cycles+=12
            elif op == 0xEA:
                address=read(pc)|read(pc+1)<<8;pc+=2
                if address == 0x2100:bank=a
                else:mem[address]=a
                cycles+=16
            elif op in (0xCD,0xC3):
                address=read(pc)|read(pc+1)<<8;pc+=2
                if op == 0xCD:push(pc)
                pc=address;cycles+=24 if op==0xCD else 16
            elif op == 0xC9:
                pc=pop();cycles+=16
            elif op == 0:cycles+=4
            else:raise ValueError(f'invalid opcode {op:02x} in bank {bank}')
        raise AssertionError('entry did not finish')

    def test_all_incoming_banks_and_flags(self):
        rom=self.build()
        for bank in (1,3,13,16,63):
            for flags in range(0,256,16):
                a,f,sp,mapped,cycles,mem=self.execute(rom,bank,flags)
                self.assertEqual((a,f,sp,mapped),(1,flags,0xDFE0,1))
                self.assertEqual([mem[x] for x in (0xFF91,0xFFDA,0xFFE4,0xFF99,0xDC09)],[1]*5)

    def test_early_unmapped_control_is_rejected(self):
        self.execute(self.parent,1,0xC0)
        for bank in (3,13,16,63):
            with self.assertRaisesRegex(ValueError,'invalid opcode'):
                self.execute(self.parent,bank,0xC0)

    def test_only_hook_and_checksum_change(self):
        rom=self.build()
        allowed={0x14e,0x14f}|set(range(0x1A43,0x1A49))
        self.assertTrue({i for i,(a,b) in enumerate(zip(rom,self.parent)) if a!=b}<=allowed)

    def test_changed_mapper_rejected(self):
        for address in (0x28,0x99A,0x61,0x9BE,0x7C9A):
            self.parent[address]^=1
            with self.assertRaisesRegex(ValueError,'preimage'):self.build()
            self.parent[address]^=1


if __name__ == '__main__':unittest.main()
