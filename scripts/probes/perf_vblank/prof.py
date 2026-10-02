import sys, collections
# usage: prof.py file.prof.tsv [minframe]
rows=[l.split('\t') for l in open(sys.argv[1]) if l.count('\t')==3]
seg=collections.Counter(); cnt=collections.Counter(); frames=set(); tot=[]
prev=None; start=None
for f,pc,c,ly in rows:
    f=int(f); c=int(c)
    if pc=='6D1': prev=(pc,c); start=c; frames.add(f); continue
    if prev is None: continue
    k=f'{prev[0]}->{pc}'; seg[k]+=c-prev[1]; cnt[k]+=1; prev=(pc,c)
    if pc=='81D': tot.append(c-start); prev=None
n=len(tot)
print('handler invocations',n,'mean total',sum(tot)/n)
for k,v in sorted(seg.items(), key=lambda kv:-kv[1])[:40]:
    print(f'{k:16s} per-frame {v/n:8.1f}  calls {cnt[k]:6d}  per-call {v/cnt[k]:8.1f}')
