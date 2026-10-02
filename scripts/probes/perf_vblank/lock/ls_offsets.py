import sys, collections
def load(p): return {(int(r[0]),int(r[1])): r for r in (l.split('\t') for l in open(p).read().split('\n')[1:] if l)}
a,b=load(sys.argv[1]),load(sys.argv[2])
offs=collections.Counter(); oo=collections.Counter(); shifted=0; n=0; oamfirst=0
for (s,f),r in a.items():
    q=b[(s,f)]
    if r[4]!=q[4]: oo[f-s]+=1
    if r[3]!=q[3]:
        n+=1; offs[f-s]+=1
        # does variant frame match base frame f-1 or f+1 (one-frame shift)?
        if any(a.get((s,f+d),[0]*5)[3]==q[3] for d in (-1,1)): shifted+=1
        # did OAM diverge earlier in the window?
        if any(a[(s,g)][4]!=b[(s,g)][4] for g in range(s+1,f)): oamfirst+=1
print(f"screen_diff_offsets={dict(sorted(offs.items()))} oam_diff_offsets={dict(sorted(oo.items()))} screen_diffs_matching_base_frame_pm1={shifted}/{n} preceded_by_oam_diff={oamfirst}/{n}")
