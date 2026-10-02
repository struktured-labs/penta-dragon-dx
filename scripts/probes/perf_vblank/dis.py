import sys
R=['B','C','D','E','H','L','(HL)','A']; RP=['BC','DE','HL','SP']; RP2=['BC','DE','HL','AF']; CC=['NZ','Z','NC','C']
ALU=['ADD A,','ADC A,','SUB ','SBC A,','AND ','XOR ','OR ','CP ']
ROT=['RLC','RRC','RL','RR','SLA','SRA','SWAP','SRL']
def dis(rom,bank,addr):
    def rd(a): return rom[(a if a<0x4000 else bank*0x4000+a-0x4000)]
    op=rd(addr); x,y,z=op>>6,(op>>3)&7,op&7; p,q=y>>1,y&1
    n=lambda: rd(addr+1); nn=lambda: rd(addr+1)|rd(addr+2)<<8
    def rel(): v=n(); return addr+2+(v-256 if v>127 else v)
    if op==0xCB:
        o=rd(addr+1); x2,y2,z2=o>>6,(o>>3)&7,o&7
        s=[f'{ROT[y2]} {R[z2]}',f'BIT {y2},{R[z2]}',f'RES {y2},{R[z2]}',f'SET {y2},{R[z2]}'][x2]; return s,2
    if x==0:
        if z==0: return [ 'NOP',f'LD (${nn():04X}),SP','STOP','JR ${:04X}'.format(rel()), f'JR NZ,${rel():04X}',f'JR Z,${rel():04X}',f'JR NC,${rel():04X}',f'JR C,${rel():04X}'][y], [1,3,2,2,2,2,2,2][y]
        if z==1: return (f'LD {RP[p]},${nn():04X}',3) if q==0 else (f'ADD HL,{RP[p]}',1)
        if z==2: return [ 'LD (BC),A','LD A,(BC)','LD (DE),A','LD A,(DE)','LD (HL+),A','LD A,(HL+)','LD (HL-),A','LD A,(HL-)'][y],1
        if z==3: return (f'INC {RP[p]}' if q==0 else f'DEC {RP[p]}'),1
        if z==4: return f'INC {R[y]}',1
        if z==5: return f'DEC {R[y]}',1
        if z==6: return f'LD {R[y]},${n():02X}',2
        if z==7: return ['RLCA','RRCA','RLA','RRA','DAA','CPL','SCF','CCF'][y],1
    if x==1: return ('HALT',1) if op==0x76 else (f'LD {R[y]},{R[z]}',1)
    if x==2: return f'{ALU[y]}{R[z]}',1
    if z==0:
        if y<4: return f'RET {CC[y]}',1
        return [f'LDH (${n():02X}),A',f'ADD SP,{n()}',f'LDH A,(${n():02X})',f'LD HL,SP+{n()}'][y-4],2
    if z==1:
        if q==0: return f'POP {RP2[p]}',1
        return ['RET','RETI','JP HL','LD SP,HL'][p],1
    if z==2:
        if y<4: return f'JP {CC[y]},${nn():04X}',3
        return ['LD (C),A',f'LD (${nn():04X}),A','LD A,(C)',f'LD A,(${nn():04X})'][y-4],[1,3,1,3][y-4]
    if z==3:
        if y==0: return f'JP ${nn():04X}',3
        if y==6: return 'DI',1
        if y==7: return 'EI',1
        return f'?? {op:02X}',1
    if z==4: return (f'CALL {CC[y]},${nn():04X}',3) if y<4 else (f'?? {op:02X}',1)
    if z==5:
        if q==0: return f'PUSH {RP2[p]}',1
        return (f'CALL ${nn():04X}',3) if p==0 else (f'?? {op:02X}',1)
    if z==6: return f'{ALU[y]}${n():02X}',2
    if z==7: return f'RST ${y*8:02X}',1
if __name__=='__main__':
    rom=open(sys.argv[1],'rb').read(); bank=int(sys.argv[2],0); a=int(sys.argv[3],0); cnt=int(sys.argv[4]) if len(sys.argv)>4 else 60
    for _ in range(cnt):
        s,l=dis(rom,bank,a)
        raw=bytes((rom[(a+i if a+i<0x4000 else bank*0x4000+a+i-0x4000)]) for i in range(l))
        print(f'{bank:02X}:{a:04X}  {raw.hex():8s} {s}'); a+=l
