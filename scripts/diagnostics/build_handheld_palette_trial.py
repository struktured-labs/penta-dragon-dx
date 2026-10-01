"""#25 experimental secret-area OBJ3 treatment; never a global crow recolor."""
import argparse
import hashlib
import json
from pathlib import Path
from build_later_hdma_overlap import Asm
from build_palette_window_trial import router

PARENT = '7c5afca573b80fefacfa057338ae8847bb86590f057a188112773076841972ec'
BANK = 20
ENTRY = 0x7D80
DATA = 0x7E50
COLORS = bytes.fromhex('0000 1863 4e2e 8410')

def offset(address):
    return BANK * 0x4000 + address - 0x4000

def payload():
    a = Asm(ENTRY)
    # Preserve inherited router ABI: source bank in B, caller BC stacked.
    a.db(*router()[:10])  # restore BC, save DE, D=bank/E=IE, IE=0
    for code in ('7A FE0D', '79 FE6B', '7C FE68'):
        a.db(*bytes.fromhex(code))
        a.jr(0x20, 'normal')
    a.db(*bytes.fromhex('7D E6FB FE58'))  # HL=6858 or685C only
    a.jr(0x20, 'normal')
    a.db(*bytes.fromhex('F0BA FE07'))
    a.jr(0x20, 'normal')
    a.db(*bytes.fromhex('FA80D8 FE09'))
    a.jr(0x28, 'selected')
    a.db(0xFE, 0x0A)
    a.jr(0x20, 'normal')
    a.label('selected')
    a.db(0xE5, 0x7D, 0xE6, 4, 0xC6, DATA & 255, 0x6F, 0x26, DATA >> 8)
    # Same bounded safe-window policy as the parent's four-byte publisher.
    a.db(*bytes.fromhex('F040 CB7F'))
    a.jr(0x28, 'write')
    a.db(*bytes.fromhex('F041 E603 FE01'))
    a.jr(0x20, 'wait3')
    a.db(*bytes.fromhex('F044 FE90'))
    a.jr(0x38, 'wait3')
    a.db(0xFE, 152)
    a.jr(0x38, 'write')
    a.label('wait3')
    a.db(*bytes.fromhex('F041 E603 FE03'))
    a.jr(0x20, 'wait3')
    a.label('wait0')
    a.db(*bytes.fromhex('F041 E603'))
    a.jr(0x20, 'wait0')
    a.label('write')
    a.db(*bytes.fromhex('2AE2 2AE2 2AE2 2AE2'))
    # Return the original source pointer advanced four bytes, not DATA+4.
    a.db(*bytes.fromhex('E1 23 23 23 23 C3E771'))
    a.label('normal')
    a.db(*bytes.fromhex('C32A73'))
    code = a.finish()
    assert ENTRY + len(code) <= DATA
    return code

def build(parent):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact Select02 parent required')
    if parent[offset(0x7320):offset(0x7320)+len(router())] != router():
        raise ValueError('palette-window router differs')
    # CALL mapper from20:71E9 returns at13:71EC, the original writer epilogue.
    if parent[0x371EC:0x371F1] != bytes.fromhex('7B D1 E0FF C9'):
        raise ValueError('source writer epilogue differs')
    result = bytearray(parent)
    for addr, code in [(ENTRY, payload()), (DATA, COLORS),
                       (0x71E7, bytes.fromhex('3E0D CD6100'))]:
        pos = offset(addr)
        if parent[pos:pos+len(code)] != b'\xff'*len(code):
            raise ValueError(f'bank20 cave occupied at {addr:04x}')
        result[pos:pos+len(code)] = code
    result[offset(0x7320):offset(0x7320)+3] = bytes((0xC3, ENTRY & 255, ENTRY >> 8))
    result[0x14E:0x150] = ((sum(result[:0x14E])+sum(result[0x150:]))&65535).to_bytes(2,'big')
    return bytes(result)

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    if a.output.exists() or (root/'tmp').resolve() not in a.output.resolve().parents:
        p.error('fresh repository tmp directory required')
    result = build(a.parent.read_bytes())
    a.output.mkdir(parents=True)
    (a.output/'candidate.gb').write_bytes(result)
    receipt = dict(issue=25, experimental=True, release_qualified=False,
        parent_sha256=PARENT, candidate_sha256=hashlib.sha256(result).hexdigest(),
        builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='scene09/0A stage07, bank13 OBJ3 source only; title not changed',
        colors_bgr555=['0000','6318','2E4E','1084'])
    (a.output/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt))
