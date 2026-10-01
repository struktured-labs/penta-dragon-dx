"""#45 experimental short native-fade fallback; no new RAM ownership."""
import argparse
import hashlib
import json
from pathlib import Path
from compose_ending_bgp_handoff_r518 import Asm

PARENT = 'ec8be28897810fac01a8918a0403900780015bf6703531f0f82ae259f209f21b'
BASE = 20*0x4000-0x4000


def build(parent):
    if hashlib.sha256(parent).hexdigest() != PARENT: raise ValueError('exact ec8 parent required')
    bank = parent[BASE+0x4000:BASE+0x8000]
    targets = []
    for pattern in ('F802367A23360FE1C39A09', 'F802363323360FE1C39A09'):
        needle = bytes.fromhex(pattern)
        if bank.count(needle) != 1: raise ValueError('ambiguous native fallback')
        targets.append(0x4000+bank.index(needle))
    a = Asm(0x5d00)
    a.db(0xFE,0x15)
    a.absolute(0xC2,'old')
    a.db(0x2B,0x7E,0xFE,0xDD)
    a.absolute(0xCA,'fade')
    a.db(0xFE,0xA2)
    a.absolute(0xC2,'old')
    a.db(0xF0,0xBA,0xB7)
    a.absolute(0xCA,'old')
    a.db(0xC3,targets[1]&255,targets[1]>>8)
    a.label('fade')
    a.db(0xF0,0xBA,0xB7)
    a.absolute(0xCA,'old')
    a.db(0xC3,targets[0]&255,targets[0]>>8)
    a.label('old')
    a.db(0xC3,0x1D,0x55)
    code = a.finish()
    if parent[BASE+0x4700:BASE+0x4709] != bytes.fromhex('E5F8057EFE0AC21D55'):
        raise ValueError('menu discriminator differs')
    if parent[BASE+0x5d00:BASE+0x5d00+len(code)] != b'\xff'*len(code):
        raise ValueError('occupied cave')
    result = bytearray(parent)
    result[BASE+0x4707:BASE+0x4709] = bytes.fromhex('005D')
    result[BASE+0x5d00:BASE+0x5d00+len(code)] = code
    result[0x14e:0x150] = ((sum(result[:0x14e])+sum(result[0x150:]))&65535).to_bytes(2,'big')
    return bytes(result)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent', type=Path); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); root = Path(__file__).resolve().parents[2]
    if a.output.exists() or (root/'tmp').resolve() not in a.output.resolve().parents:
        p.error('fresh repository tmp output required')
    rom = build(a.parent.read_bytes()); a.output.mkdir()
    (a.output/'candidate.gb').write_bytes(rom)
    r = dict(parent_sha256=PARENT,candidate_sha256=hashlib.sha256(rom).hexdigest(),
             builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             experimental=True,release_qualified=False,issue=45)
    (a.output/'receipt.json').write_text(json.dumps(r,indent=2)+'\n'); print(json.dumps(r))
