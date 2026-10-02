import sys, re, collections
from dis import dis
rom=open(sys.argv[2] if len(sys.argv)>2 else 'dx.gb','rb').read()
recs=[]
for l in open(sys.argv[1]):
    p=l.split('\t')
    if len(p)!=3 or not l.endswith('\n'): continue
    recs.append((int(p[0]),int(p[1],16),int(p[2])))
excl=collections.Counter(); incl=collections.Counter(); calls=collections.Counter()
frames=set(); stack=[]; total=0
def d(pc):
    if pc>=0xD0000: return dis(rom,13,pc-0xD0000)
    if pc>=0xFF80: return ('HRAM',1)
    return dis(rom,1,pc)
def tag(pc): return ('0D:%04X'%(pc-0xD0000)) if pc>=0xD0000 else ('00:%04X'%pc)
cache={}
for i in range(len(recs)-1):
    f,pc,c=recs[i]; f2,pc2,c2=recs[i+1]
    if pc==0x081D: stack=[]; continue
    if pc==0x06D1: frames.add((f,i)); stack=['HANDLER']
    cost=c2-c
    if cost<0 or cost>60000: continue
    total+=cost
    excl[tag(pc)]+=cost
    for s in set(stack): incl[s]+=cost
    if pc not in cache: cache[pc]=d(pc)
    s,l=cache[pc]
    op=s.split()[0]
    nxt=pc+l
    if op=='CALL' and pc2!=nxt:
        t=tag(pc2); stack.append(t); calls[t]+=1
    elif op in('RET','RETI') and pc2!=nxt and len(stack)>1:
        stack.pop()
n=len(frames)
print('frames',n,'mean per frame',total/n)
print('--- inclusive by routine (per frame, units; 912=1 line)')
for k,v in sorted(incl.items(),key=lambda kv:-kv[1])[:40]:
    print(f'{k:10s} {v/n:8.1f}  calls/frame {calls[k]/n:5.2f}')
print('--- exclusive hot instructions')
for k,v in sorted(excl.items(),key=lambda kv:-kv[1])[:40]:
    pc=int(k[3:],16)+(0xD0000 if k.startswith('0D') and int(k[3:],16)>=0x4000 else 0)
    print(f'{k} {v/n:8.1f}  {cache.get(pc,("?",0))[0]}')
