"""Issue #27: experimental graphics scene-cache fix, not full qualification.

Native D880=$0B is a sound alias during low-health arenas. Resolve it through
FFB7 only for canonical arena IDs $0C..$14. Never write either native field.
The attribute dispatcher still requires separate investigation/qualification.
"""
import argparse
import hashlib
import json
from pathlib import Path
from compose_ending_bgp_handoff_r518 import Asm

PARENT = 'd744124d3d161247e0584bb39e8db1243ade4e428cbc15f82a85c10d0a4ac4d5'
ENTRY = 0x6DA7


def offset(bank, address):
    return bank * 0x4000 + address - 0x4000


def payload():
    a = Asm(ENTRY)
    a.db(*bytes.fromhex('FA80D8 FE0B'))
    a.jr(0x20, 'compare')
    a.db(*bytes.fromhex('F0B7 D60C FE09'))
    a.jr(0x38, 'arena')
    a.db(0x3E, 0x0B)
    a.jr(0x18, 'compare')
    a.label('arena')
    a.db(0xC6, 0x0C)
    a.label('compare')
    # Preserve comparison AF across mapper-only return. HL and all other
    # registers have the same contract as the replaced scene-cache prefix.
    a.db(*bytes.fromhex('210DDF BE F5 3E0D C3926F'))
    return a.finish()


def build(parent):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact combined presentation parent required')
    start = offset(13, 0x6F90)
    if parent[start:start+8] != bytes.fromhex('FA80D8 210DDF BE C8'):
        raise ValueError('scene-cache prefix changed')
    if parent[0x9BE:0x9C4] != bytes.fromhex('E099 EA0021 C9'):
        raise ValueError('mapper-only ABI changed')
    result = bytearray(parent)
    for addr, code in ((0x6F92, bytes.fromhex('CDBE09 C3A76D')),
                       (ENTRY, payload())):
        pos = offset(20, addr)
        if parent[pos:pos+len(code)] != b'\xff' * len(code):
            raise ValueError('private bank20 cave occupied')
        result[pos:pos+len(code)] = code
    # First mapping returns into bank20:6F95. The private helper pushes AF
    # and jumps through the same CALL site to return into bank13:6F95.
    result[start:start+8] = bytes.fromhex('3E14 CDBE09 F1 C8 00')
    result[0x14E:0x150] = ((sum(result[:0x14E])+sum(result[0x150:])) & 65535).to_bytes(2, 'big')
    return bytes(result)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.output.exists() or (root/'tmp').resolve() not in args.output.resolve().parents:
        p.error('fresh repository tmp output required')
    result = build(args.parent.read_bytes())
    args.output.mkdir(parents=True)
    (args.output/'candidate.gb').write_bytes(result)
    receipt = dict(issue=27, experimental=True, release_qualified=False,
                   parent_sha256=PARENT,
                   candidate_sha256=hashlib.sha256(result).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   scope='graphics scene cache only; native sound state unchanged; dispatcher pending')
    (args.output/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt))
