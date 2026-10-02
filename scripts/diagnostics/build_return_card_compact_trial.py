"""#45 isolate compact card uploads from unchanged return-to-game uploads."""
import argparse
import hashlib
import json
from pathlib import Path
from build_return_palette_compact_trial import body

PARENT = '8ac7fbe3b290f4743280961541fb81746046e89bbdabde6f2b914e73fd60888c'


# Re-pin (docs/audit/release-lock-20261001-repin.md): the release-lock chain
# defers #14 and #34. Parent 3540f75e... yields byte-identical
# changes (same offsets, preimages and values) as on the original 8ac7fbe3...
REPINNED_PARENT = '3540f75e14b7634d0dda6afb5199e4abc6c9a47c03fbb09eb2b610dd23ac7241'


def build(parent):
    if hashlib.sha256(parent).hexdigest() not in (PARENT, REPINNED_PARENT):
        raise ValueError('exact deadline trial14 required')
    result = bytearray(parent)
    cursor = 0x5083
    for shade, old in ((0xe4,0x5ac0),(0x90,0x5998),(0x40,0x5878),(0,0x5760)):
        routine = bytes.fromhex('F0 68 F5 CD F8 5B') + body(shade, True)
        if cursor + len(routine) > 0x5519:
            raise ValueError('compact card cave exhausted')
        offset = 20*0x4000 + cursor - 0x4000
        if parent[offset:offset+len(routine)] != b'\xff'*len(routine):
            raise ValueError('compact card cave occupied')
        result[offset:offset+len(routine)] = routine
        needle = bytes((0xcd,old&255,old>>8))
        site = parent.find(needle,0x51c20,0x51c89)
        if site < 0 or parent.find(needle,site+1,0x51c89) >= 0:
            raise ValueError('missing/ambiguous card-only call')
        result[site+1:site+3] = cursor.to_bytes(2,'little')
        cursor += len(routine)
    result[0x14e:0x150] = ((sum(result[:0x14e])+sum(result[0x150:]))&65535).to_bytes(2,'big')
    return bytes(result)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();root=Path(__file__).resolve().parents[2]
    if a.output.exists() or (root/'tmp').resolve() not in a.output.resolve().parents:
        p.error('fresh repository tmp output required')
    rom=build(a.parent.read_bytes());a.output.mkdir()
    (a.output/'candidate.gb').write_bytes(rom)
    r=dict(issue=45,experimental=True,release_qualified=False,parent_sha256=PARENT,
           candidate_sha256=hashlib.sha256(rom).hexdigest(),
           builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           compact_body_source_sha256=hashlib.sha256(Path(__file__).with_name('build_return_palette_compact_trial.py').read_bytes()).hexdigest())
    (a.output/'receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
