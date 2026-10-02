"""Combine independently scoped Shalamar death and Troop repeat repairs."""
from pathlib import Path
import hashlib
import json
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'scripts/diagnostics')]
import compose_troop_repeat_r457c as troop
import compose_shalamar_death_r458b as shalamar

OUT = ROOT/'tmp/boss-repairs-r462'


def build(source):
    # Both independent builders authenticate the exact retained base.
    a, b = troop.build(source), shalamar.build(source)
    changes = [{i for i,(x,y) in enumerate(zip(source,child))
                if x!=y and i not in (0x14D,0x14E,0x14F)} for child in (a,b)]
    if changes[0] & changes[1]: raise ValueError('repair footprints overlap')
    result = bytearray(source)
    for child, offsets in zip((a,b),changes):
        for offset in offsets: result[offset]=child[offset]
    troop.update_checksums(result)
    return bytes(result)


if __name__=='__main__':
    source=shalamar.BASE.read_bytes(); candidate=build(source)
    OUT.mkdir(exist_ok=True); path=OUT/'candidate.gb'
    if path.exists() and path.read_bytes()!=candidate:
        raise ValueError('immutable candidate collision')
    path.write_bytes(candidate)
    receipt=dict(experimental=True,promotable=False,base_sha256=troop.BASE_SHA,
                 candidate_sha256=hashlib.sha256(candidate).hexdigest(),
                 components=['r457c Troop 120-window exact-repeat delay','r458b Shalamar HP-zero native-publication guard'])
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))
