"""Issue #21 trial: defer VBlank during native 16-piece boss publication.

Save/restore IE on the stack; keep Timer/STAT enables unchanged. The existing
per-entry emitter can still EI. No persistent RAM or buffer alternation changes.
Experimental: timing, interrupt nesting, and other bosses remain unqualified.
"""
import argparse
import hashlib
import json
from pathlib import Path
from build_boss_shadow_atomic import PARENTS

START, END = 0x2b91, 0x2bda
OLD = bytes.fromhex(
    '1100C03E10CDE409E52185DC23234E2346E1'
    'C5CDBA10C1C579C6104FCDBA10C1C578C61047CDBA10C178C6104779C6104FCDBA10'
    '1100C13E10CDE4092100C03E10D7014000CDB309C9')


def body():
    # Entry HL already points at the boss descriptor. Preserve it while
    # fetching exactly the same B/C coordinates. Keep all four emitter calls.
    code = bytes.fromhex('F0FFF5E6FEE0FF 1110C0 E52187DC4E2346E1')
    code += OLD[0x2ba3-START:0x2bc5-START]
    # Native final registers: BC=0, DE=C150, HL=C050, A=10, F=0.
    code += bytes.fromhex('1110C1 2110C0 014000 CDB309 F1E0FF 3E10B7 C9')
    assert len(code) <= END-START
    return code.ljust(END-START, b'\0')


def build(parent):
    if hashlib.sha256(parent).hexdigest() not in PARENTS:
        raise ValueError('unreviewed parent')
    if parent[START:END] != OLD:
        raise ValueError('boss routine preimage differs')
    result = bytearray(parent)
    result[START:END] = body()
    result[0x14e:0x150] = ((sum(result[:0x14e])+sum(result[0x150:])) & 65535).to_bytes(2, 'big')
    return bytes(result)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    out = args.output.resolve()
    root = Path(__file__).resolve().parents[2]
    if out.exists() or (root/'tmp').resolve() not in out.parents:
        p.error('fresh repository tmp output required')
    parent = args.parent.read_bytes()
    candidate = build(parent)
    out.mkdir()
    (out/'candidate.gb').write_bytes(candidate)
    receipt = dict(issue=21, experimental=True, release_qualified=False,
                   parent_sha256=hashlib.sha256(parent).hexdigest(),
                   candidate_sha256=hashlib.sha256(candidate).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (out/'build-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt))
