import sys, collections
def load(p):
    return {(r[0], r[1]): r for r in (l.split('\t') for l in open(p).read().split('\n')[1:] if l)}
a, b = load(sys.argv[1]), load(sys.argv[2])
keys = sorted(set(a) & set(b), key=lambda k: (int(k[0]), int(k[1])))
scr = [k for k in keys if a[k][3] != b[k][3]]
oam = [k for k in keys if a[k][4] != b[k][4]]
bad_states = sorted({k[0] for k in scr}, key=int)
byscene = collections.Counter(a[k][2] for k in scr)
print(f"frames={len(keys)} missing={len(set(a)^set(b))} screen_diff={len(scr)} oam_diff={len(oam)} states_with_diff={len(bad_states)}/{len({k[0] for k in keys})} first={scr[0] if scr else 'none'} scenes={dict(byscene)}")
