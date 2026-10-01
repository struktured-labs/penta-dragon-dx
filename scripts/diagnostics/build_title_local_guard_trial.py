"""#35 experimental title-only writer, preserving the native DC09 mapper shadow."""
import argparse
import hashlib
import json
from pathlib import Path
from build_later_hdma_overlap import Asm
from build_title_cram_guard_trial import PARENT, OFFSET, OLD

ENTRY = 0x6B80
DATA = 0x6C20


def offset(address):
    return 20 * 0x4000 + address - 0x4000


def payload():
    a = Asm(ENTRY)
    # Title caller always supplies6838 (BG0 alias and BG7 share this ramp).
    # Save all live pairs; D holds IE while the private data bank is mapped.
    a.db(*bytes.fromhex('C5 D5 E5 F0FF 57 AF E0FF'))
    a.db(0x21, DATA & 255, DATA >> 8, 0x06, 2, 0x0E, 0x69)
    a.label('chunk')
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
    a.db(*bytes.fromhex('2AE2 2AE2 2AE2 2AE2 05'))
    a.jr(0x20, 'chunk')
    # Carry IE on stack through mapper-only return. Source-bank epilogue
    # restores it only after the bank, stack, and live registers are coherent.
    a.db(*bytes.fromhex('7A E1 23 23 23 23 23 23 23 23 D1 C1 0E00 F5 3E0D C3596A'))
    code = a.finish()
    assert ENTRY + len(code) <= DATA
    return code


def build(parent):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact handheld parent required')
    if parent[OFFSET:OFFSET+9] != OLD:
        raise ValueError('title helper differs')
    # Both known title call sites load the same native ramp.
    if parent[0x36A7D:0x36A83] != bytes.fromhex('213868 CD576A'):
        raise ValueError('first title source differs')
    if parent[0x36A87:0x36A8C] != bytes.fromhex('2E38 CD576A'):
        raise ValueError('second title source differs')
    result = bytearray(parent)
    for addr, code in ((0x6A59, bytes.fromhex('CDBE09') + bytes((0xC3, ENTRY & 255, ENTRY >> 8))),
                       (ENTRY, payload()), (DATA, parent[0x36838:0x36840])):
        pos = offset(addr)
        if parent[pos:pos+len(code)] != b'\xff' * len(code):
            raise ValueError(f'occupied bank20 cave {addr:04x}')
        result[pos:pos+len(code)] = code
    result[OFFSET:OFFSET+9] = bytes.fromhex('3E14 CDBE09 F1 E0FF C9')
    result[0x14e:0x150] = ((sum(result[:0x14e])+sum(result[0x150:])) & 65535).to_bytes(2,'big')
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
    receipt = dict(issue=35, parent_sha256=PARENT, experimental=True,
                   release_qualified=False,
                   candidate_sha256=hashlib.sha256(result).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (a.output/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt))
