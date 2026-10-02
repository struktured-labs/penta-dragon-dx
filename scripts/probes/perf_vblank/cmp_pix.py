import sys
def load(p):
    return [l.split('\t') for l in open(p).read().split('\n')[1:] if l]
a, b = load(sys.argv[1]), load(sys.argv[2])
n = min(len(a), len(b)); diff = [i for i in range(n) if a[i][2] != b[i][2]]
scenes = sorted({r[1] for r in a})
print(f"frames={n} identical={n-len(diff)} first_diff={a[diff[0]][0]+' scene '+a[diff[0]][1] if diff else 'none'} scenes={','.join(scenes)}")
