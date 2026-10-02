"""Read-only LR35902 walk of actual ROM gateway and installed dispatcher."""

def walk(rom: bytes, scene: int):
    ram = bytearray(65536)
    a0 = 13*16384+0x7BB2-0x4000
    b0 = 13*16384+0x7C4D-0x4000
    ram[0xDA60:0xDB00] = rom[a0:a0+46]+rom[b0:b0+114]
    # The installed semantic runtime at DBA4 (bank13 569A/56CA/56FA, 77 bytes).
    # #27's direct scene resolver lives at DBDF inside it and is CALLed by
    # the DABB scene read on the release-lock candidate.
    ram[0xDBA4:0xDBA4+77] = b''.join(
        rom[13*16384+address-0x4000:13*16384+address-0x4000+length]
        for address, length in ((0x569A, 36), (0x56CA, 36), (0x56FA, 5)))
    ram[0xD880] = scene
    ram[0xFF70] = 1
    ram[0xFFB7] = 2
    ram[0xC100:0xC104] = bytes.fromhex('9334B142')
    reg = dict(a=0,b=0x12,c=0x34,d=255,e=0x56,h=0x98,l=0)
    pc, sp, bank, z, carry = 0x18, 0xC100, 1, False, True
    visited=[]; writes=[]
    def read(addr):
        if addr < 0x4000: return rom[addr]
        if addr < 0x8000: return rom[bank*16384+addr-16384]
        return ram[addr]
    def word(addr): return read(addr) | read(addr+1)<<8
    def hl(): return reg['h']*256+reg['l']
    def sethl(v): reg['h'],reg['l']=(v&65535)>>8,v&255
    def put(addr,v):
        nonlocal bank
        if addr == 0x2100: bank=v
        else: ram[addr]=v;writes.append((addr,v))
    def push(v):
        nonlocal sp
        sp-=2;put(sp,v&255);put(sp+1,v>>8)
    def pop():
        nonlocal sp
        v=word(sp);sp+=2;return v
    for step in range(300):
        if pc in (0xDBA4,0xDA60):
            assert sp==0xC100 and word(sp)==0x3493 and word(sp+2)==0x42B1
            assert hl()==0x9800 and bank==1
            assert all(0xC0E0 <= addr < 0xC104 or addr in (0xDC09, 0xFF99)
                       for addr, value in writes), "unexpected memory side effect"
            return pc,visited
        visited.append(pc);op=read(pc);pc+=1
        if op==0x7A:reg['a']=reg['d']
        elif op==0x78:reg['a']=reg['b']
        elif op==0x3C:reg['a']=(reg['a']+1)&255;z=reg['a']==0
        elif op==0x3D:reg['a']=(reg['a']-1)&255;z=reg['a']==0
        elif op in (0xC3,0xC2,0xCA,0xCD,0xC4):
            target=word(pc);pc+=2
            taken=op in (0xC3,0xCD) or (op==0xCA and z) or (op in (0xC2,0xC4) and not z)
            if taken:
                if op in (0xCD,0xC4):push(pc)
                pc=target
        elif op==0xC9:pc=pop()
        elif op==0xC0:
            if not z:pc=pop()
        elif op==0xC6:
            v=read(pc);pc+=1;carry=reg['a']+v>255;reg['a']=(reg['a']+v)&255;z=reg['a']==0
        elif op in (0x3E,0x06):reg['a' if op==0x3E else 'b']=read(pc);pc+=1
        elif op==0xEA:put(word(pc),reg['a']);pc+=2
        elif op==0xFA:reg['a']=read(word(pc));pc+=2
        elif op==0xE0:put(0xFF00+read(pc),reg['a']);pc+=1
        elif op==0xF0:reg['a']=read(0xFF00+read(pc));pc+=1
        elif op==0xE5:push(hl())
        elif op==0xE1:sethl(pop())
        elif op==0xF8:
            v=read(pc);pc+=1;sethl(sp+(v if v<128 else v-256));z=False;carry=(sp&255)+v>255
        elif op==0x7E:reg['a']=read(hl())
        elif op==0xFE:v=read(pc);pc+=1;z=reg['a']==v;carry=reg['a']<v
        elif op==0xE6:reg['a'] &= read(pc);pc+=1;z=reg['a']==0;carry=False
        elif op==0xD6:
            v=read(pc);pc+=1;carry=reg['a']<v;reg['a']=(reg['a']-v)&255;z=reg['a']==0
        elif op==0xAF:reg['a']=0;z=True;carry=False
        elif op==0xB7:z=reg['a']==0;carry=False
        elif op==0x23:sethl(hl()+1)
        elif op==0x2B:sethl(hl()-1)
        elif op==0x36:put(hl(),read(pc));pc+=1
        elif op in (0x18,0x20,0x28,0x38,0x30):
            v=read(pc);pc+=1
            if op==0x18 or (op==0x20 and not z) or (op==0x28 and z) or (op==0x38 and carry) or (op==0x30 and not carry):pc+=v if v<128 else v-256
        else:raise AssertionError(f'unknown {op:02X} at {pc-1:04X}')
    raise AssertionError('dispatch did not terminate')


