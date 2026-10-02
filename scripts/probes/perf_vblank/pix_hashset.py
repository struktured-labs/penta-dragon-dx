import sys
def load(p): return [l.split("\t") for l in open(p).read().split("\n")[1:] if l]
a,b=load(sys.argv[1]),load(sys.argv[2])
A=set(r[2] for r in a)
nb=[r for r in b if r[2] not in A]
g=[r for r in b if r[1]=="02"]; gn=[r for r in g if r[2] not in A]
def first(rows,s):
  for r in rows:
    if r[1]==s: return r[0]
print(f"hash_not_in_base={len(nb)}/{len(b)} s02={len(g)} s02_not_in_base={len(gn)} first02 base={first(a,'02')} var={first(b,'02')}")
